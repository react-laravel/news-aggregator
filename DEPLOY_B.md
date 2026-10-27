# News 的 GitHub 托管构建与 B 发布方案（待授权）

仓库：`react-laravel/news-aggregator`。补丁精确父提交：`038dd4cb63a594d695638ae6a55c2965d24d94f6`，原树 `a20c34fe1444a97811a20957d73d5ddba9f67aa5`，80 个已跟踪文件与 A 退役源逐 Git blob 一致。此文是新增的 B 增量说明，原 `DEPLOY.md` 不改。

本方案尚未创建账号、长期 key、GitHub Secrets、提交或远端 refs；未切换任何 B 运行代码、停止服务、冻结 cgroup 或执行数据库变更。当前 B 仍使用已完成迁移的单一运行版。

## 构建和权限

GitHub `ubuntu-24.04` + Node `24.16.0` 执行原锁文件的 `npm ci`、Prisma 客户端生成、lint、单元测试、发布协议测试、Next 构建，再输出独立运行包和编译采集器。使用假 `DATABASE_URL`，不向 B 读取 ENV，不 migrate、seed、执行采集或发部署通知。Next 原依赖、业务采集/分类/翻译/保存逻辑和两份 migration SQL 均保留。B 不安装 npm、开发依赖或构建工具。

Actions 总权限仅 `contents: read`。PR 只构建；`main` push 自动发布，手动调度默认仅验证构建，显式勾选 publish 才发布。部署使用 `news-b` Environment，授权时将 Environment 的部署分支限定为 `main`。只设置此仓库的 `NEWS_B_SSH_KEY`、`NEWS_B_KNOWN_HOSTS`，不复用其他仓库 key，也不写数据库、Brave、AI、代理或管理员凭据到 GitHub。旧 A 专属 self-hosted workflow 继续保持停用；新补丁取代原文件后才启用新的托管 workflow。

拟新建专属系统账号 `news-deploy`，无密码、不加入运行账号组，授权公钥只能执行 root-owned `news-ssh-gateway.py`。authorized_keys 采用 `restrict,command="/usr/local/libexec/news-ssh-gateway"`，SSH Match 禁止 TTY、端口/代理/X11 转发、用户 rc 与密码登录，授权文件 root-owned；没有任意 shell、SFTP/SCP 或 sudo 参数。gateway 只接受 `receive|publish|validate` 加 40 位小写 SHA。

账号能写的只有 `/var/www/news.dogeow.com/releases` 内代码、`/var/lib/dogeow-news-deploy` 内上传/发布状态；外层 `current -> releases/current`、共享目录、私有 ENV、固定运行入口、任务锁 inode 和系统服务配置均归 root。sudoers 唯一授权为：

```
/usr/bin/systemctl restart dogeow-test-news-web.service
```

不授予 timer、采集服务、其他站点、Nginx、数据库、freeze/kill 或通用 sudo 权限。此 key 具有 **News 应用代码发布权**；发布后的应用仍拥有 News 自己既有的数据库和运行凭据权限，这一固有代码权限不能被“key 不能直接读 ENV”掩盖。

## 为什么必须改变管理采集入口

原代码有三个真实入口：CLI `scripts/ingest-news.ts`、全量 `POST /api/admin/jobs/run`、单源 `POST /api/admin/sources/[id]/ingest`。两个 HTTP 路由都直接 `await` 同一 Web 进程内的采集函数；没有后台队列或 detached 子进程。仅见 oneshot inactive 不能证明网页没在抓取。

原 `findFirst(status=running, startedAt>=20分钟前)` 再 `create` 既有竞态，也不会保护任务超过 20 分钟的情况。补丁保留这个业务提示，但不再把它当发布锁。两个生产 HTTP 路由现在 `await` 固定受限采集子进程，仍返回原 summary JSON，失败仍为原 HTTP 500 形状。全量和单源共用同一个固定 collector 入口；定时器也通过它。手动任务用原私有 `web` 环境分组，定时任务用原 `ingest` 分组，凭据不搬出 B。开发模式仍可直接调用原函数。

固定包装器先以 `O_NOFOLLOW` 打开 root-owned `/var/lib/dogeow-news-lock/ingest.lock` 的稳定 inode，获取内核排他 flock，**持锁后**检查维护标记，然后把锁 FD 继承到真正运行 `ingest.cjs` 的 Node 进程。所有实际网络/付费 API/数据库保存、失败终态、Prisma disconnect 完成并进程退出后，内核才释放锁。网页超时或客户端断连不会终止子进程或提早释放锁。

发布器先原子建立维护标记阻止后来任务，再等待同一个 flock。已有任务完整退出前不会切换、重启或删旧代码。它持锁完成原子 current 切换、仅重启本站 web、健康验证及旧版清理，失败则在同锁内回退到上一个锁感知版本。回退本身不健康时保持采集维护门关闭，交给管理员恢复。定时器平时完全不 stop/start/restart；期间自然到点的 tick 在 DB/网络之前返回 75，下一次仍按原 `*-*-* 00/2:44:44 UTC`（台北 00/2:44:44）继续，不主动补抓。

只允许一个手动 collector。因它现在是子进程，与 Web 共用本站 cgroup，拟把本 Web 单元预算改为 MemoryHigh 384M / MemoryMax 576M / TasksMax 96；原定时采集服务预算不改。无需扩展其他站点资源或权限。

## 首轮改为 root 持久认领和独立系统任务

旧首轮补丁 `907d9d860b305677…` 的独立复核发现：等待中的 publisher 超时/死亡会删掉已验包，root 却仍可能终止旧 Web；root 在 kill 后断连又没有可执行恢复。原补丁、ZIP、报告及源码已完整封存至 `reviews/initial-907d9d860b305677`。本修订不以“再查一次 PID”代替责任转移。

publisher 首轮只校验压缩包并原子写 `first-publish-ready.json`（SHA、32位 nonce、归档 SHA256、逐文件哈希、过期时间），随后释放 publish.lock，仅观察 root 状态；不展开到 releases、不切 current、不 restart。未认领的超时可以同锁取消并删除自己的上传；**已被 root 认领的包永远不在 publisher 的清理路径里**。GHA/SSH 消失不等于发布成功。

管理员在完整 GitHub 构建产物已收到后，从 ready 取出同一 SHA/nonce，执行固定 root 命令：

```
/usr/local/libexec/news-first-control claim <SHA> <nonce>
```

此命令先启动 root-only `dogeow-news-first-takeover.service`（没有状态时持续 idle、不持执行锁、不动站点），再在 publish.lock 内将包复制至 root-owned `CONTROL/claims/<SHA>-<nonce>/runtime.tar.gz`，完整重验清单/哈希、展开并校验运行包、fsync 文件和目录，再原子提交 root-owned `first-state.json`。canonical archive 为 root:root 0400，控制目录不允许部署/运行账号写；原上传这时才能删。root 只在原站仍服务、完整不可变包已独立持有后进入维护。这里的“root 认领”不依赖 publisher 活着或任何 PID。

真正接管由独立 systemd 服务执行；`Restart=always`、持久阶段日志和 root 执行锁支持进程被杀/机器重启后同一 SHA+nonce 重入。调用 SSH 断线不会结束系统任务。固定恢复/取消命令是：

```
/usr/local/libexec/news-first-control resume <SHA> <nonce>
/usr/local/libexec/news-first-control cancel <SHA> <nonce>
```

持久 NoStart/NoRestart drop-in 使用同目录临时正规文件，完整写入、保留原 uid/gid/mode 并 fsync 后才原子 replace，最后 fsync 目录；重入不会截断已持久屏障。此窄修仅新增本地真实 IO 硬退出矩阵，不改变任务排空/激活协议、应用构建输入或权限边界。

阶段：`claimed → maintenance → draining → kill_committed → old_dead → launcher_ready → release_ready → switch_intent → starting → healthy → open_intent → completed`。每个阶段原子落盘并 fsync。取消还使用可重入 `aborting → aborted`。所有 ready、状态、取消和完成都绑定 SHA+nonce；不同 nonce/stale result 拒绝，完全不使用 PID 身份。

- **commit 前**：维护门暂停新请求，仅停本站 timer，从不 stop 活着的 collector。先持久写 `Restart=no` 和 `ConditionPathExists=!legacy-no-start`，避免控制器死亡/重启时旧包自动复活。等 oneshot 全退出及全部 running 记录清零；冻结固定 cgroup，在 `IngestJob` 表 ACCESS EXCLUSIVE 事务屏障内再次证明无 running/active/未提交事务/未知角色连接，并清除旧 idle 连接。任一条件不满足就释放屏障后 thaw 等任务完整完成，不降低排空条件。
- 最后取消/过期检查、持久 `kill_committed` 和随后的 cgroup.kill 在同一 publish.lock 临界区，取消写入也用该锁。**`kill_committed` 是不可逆点**；它已包含完整安全证明，即使此后 populated 仍为1，也可能是已发 SIGKILL 尚未完成，绝不能误判“尚未杀”而恢复旧协议。该阶段恢复须重新确认固定冻结组/数据库屏障并完成同一新锁包；绝不凭 phase 单独跳过排空。
- **commit 前取消/过期**：持久 `aborting`，完整恢复原 launcher、旧 current 和原 Restart 状态，必要时 thaw/启动原 Web，按原 307/401/login 契约验收。ingest 单元预装 `ConditionPathExists=!bootstrap-maintenance`，所以恢复 Persistent timer 时维护中补偿 tick 不会真的采集；最后才开门并记 `aborted`。中途再次死亡可以同命令继续恢复。这是完整旧协议恢复，不混用新旧入口。
- **commit 后**：只对仍冻结、经完整证明无业务任务的本站固定 cgroup 写 cgroup.kill，等 populated=0 才 systemctl stop 空 unit。随后服务自身安装已暂存的固定 launcher、移动已验运行包、切换并启动锁感知新 Web，完全不等待原 publisher。源上传删掉也无影响；工作 release 若中断/丢失可从 root canonical archive 在独立临时目录重新展开，完整校验和fsync后原子换入；重复中断不会卡在半解压目录。校验不符会拒绝，不自动信任替换包。
- 新包 `/healthz` 的 SHA+SELECT1、原匿名认证契约及静态资产验证通过后，恢复原 timer 节奏。任何激活/恢复重启都先关门并等待同一 ingest flock，防止控制器在开门后死亡又重入时杀掉新采集任务。打开门后才记 `completed/public_open=true`，publisher 此时才可报告真实发布成功。completed 历史重入只报告完成，不能把未来日常更新回滚到首版。

新包启动失败时，systemd 控制器保留 root canonical 包并继续从 durable phase 恢复；固定 `resume` 可独立完成，不需要 GHA 重跑、死 publisher、A 或临时 SSH 会话。没有“只保留503、但无恢复命令”的终态。底层故障/校验不符仍应拒绝危险操作，由管理员修复同一受保护包/配置后 resume；不自动启动已终止的旧无锁包。

成功后 root 可执行 `news-first-control finalize <SHA> <nonce>` 停用已完成的一次性控制服务；completed 元数据保留，canonical 包只在完成后清理。安全取消后，可执行 `retire-aborted <SHA> <nonce>` 归档旧身份并清理匹配 ready，再发新请求；不同 nonce 不会悄悄接管历史状态。

以上 root 服务/命令仅 root 可调用，不进入部署 key 的 sudoers。key 依旧只有固定 restart 本站 Web；没有 timer、freeze/kill、数据库或通用命令权限。源码建账/终态证明不变：`ingestNews` 178行、单源216行 await 建账之后才发起 adapter/付费调用、翻译和持久化，全部 await 后才标终态，CLI 再 await disconnect 后退出。schema、migrations、采集业务和锁文件不改。

依据：[systemd freeze/stop](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html)、[Linux cgroup freezer/kill](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html)、[PostgreSQL显式锁](https://www.postgresql.org/docs/18/explicit-locking.html)、[活动快照](https://www.postgresql.org/docs/18/monitoring-stats.html)。真实 freeze/kill/安装仍未执行；新故障矩阵仅用临时文件、假宿主和独立子进程 `os._exit`，不触碰生产。

## 磁盘、回退与验收

接收上限 96MiB，展开上限 200MiB。接收和展开各自先检查余盘，始终至少留 1GiB；不够就拒绝，绝不自动删未知文件腾空间。包只含正则文件、允许的 runtime 目录、编译采集器与 Prisma 客户端；拒绝符号/硬链接、路径越界、重复路径、ENV、SSH、凭据配置、可写缓存和校验不一致。解压后删除上传包，本站缓存仅通过已有 shared/cache 连接，不覆盖状态。

成功后 B 仅保留当前一个程序版本。健康失败时优先保留原锁版并回退，旧码不会在任务仍占锁时删除。成功后若未来要恢复历史代码，由 GitHub 保留的构建产物/明确 SHA 重新构建发布；不在 B 常驻多份版本。不能自动 migrate、seed、真实采集、修改管理员 token、代理凭据或发送通知。

本修订已用 A 原有依赖重新完成 lint、11项Vitest、Next 16.2.10完整构建及严格打包；该全流程包含39项Python。其后仅root恢复解压与IO回归变动，最终40项Python已在Linux重新通过，应用构建输入逐字节未变。故障矩阵包含25个不同 `os._exit` 点，均用全新解释器恢复；另用真实临时flock证明开门后崩溃恢复会等待采集任务。真实临时归档验证root claim、上传删改隔离、nonce/过期拒绝、canonical rename后/state前孤儿同身份恢复。新编译采集器闭包实际加载后，应用网络调用=0、DB写=0、disconnect=1。新版SQL客户端也在 A 原只读库完成快照协议校验，未拿表锁、终止连接或执行DDL。

新实验包压缩57,385,238B，展开170,616,208B，2,843文件；manifest父SHA仅为夹具标记，不是远端新提交。首次root canonical复制阶段还会短暂多一份压缩包，按实际大小额外核查至少1GiB，不靠删除旧运行版腾空间。原B离线往返（15项旧版协议测试、零socket/DB写、最低余盘1,329,852,416B）只作为未变运行打包/依赖闭包的历史证据，不冒称新版durable root controller在B真实运行验收。

本次未安装任何账号/长期key/Secrets/新root服务，未提交远端refs，未真实freeze/kill/迁移schema/采集/付费调用或通知；Mac未下载运行包/大依赖。A本组隔离候选在验证后精确清理，原 A 源码、依赖、ENV、readonly库留存。新的精确父补丁和故障矩阵须经独立复核后，才可向用户申请这一个仓库的长期权限。

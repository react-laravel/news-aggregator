import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
const root = process.cwd();
const req = createRequire(path.join(root, 'package.json'));
const revision = process.argv[2];
if (!/^[0-9a-f]{40}$/.test(revision || '')) throw Error('Expected exact revision');
const out = path.join(root, '.news-runtime');
await fs.mkdir(out, { recursive: false });
const standalone = path.join(root, '.next/standalone');
await fs.cp(standalone, out, { recursive: true, dereference: true });
for (const name of ['.next/static', 'public', 'prisma']) {
  await fs.cp(path.join(root, name), path.join(out, name), { recursive: true, dereference: true });
}
const temp = path.join(root, '.next/news-ci');
await fs.mkdir(temp, { recursive: true });
const built = await req('esbuild').build({
  absWorkingDir: root, entryPoints: ['scripts/ingest-news.ts'], outfile: path.join(temp, 'ingest.cjs'),
  bundle: true, platform: 'node', format: 'cjs', target: 'node24', packages: 'external',
  tsconfig: path.join(root, 'tsconfig.json'), metafile: true, logLevel: 'silent',
});
if (!Object.keys(built.metafile.inputs).some((n) => n.endsWith('src/lib/news/ingest.ts'))) throw Error('Collector was not bundled');
await fs.copyFile(path.join(temp, 'ingest.cjs'), path.join(out, 'ingest.cjs'));
const { nodeFileTrace } = req('next/dist/compiled/@vercel/nft');
const entries = ['next/dist/server/next.js', 'next/dist/server/lib/start-server.js', '@prisma/client', '@prisma/adapter-pg'].map((name) => req.resolve(name));
entries.push(path.join(temp, 'ingest.cjs'));
const traced = await nodeFileTrace(entries, { base: root, processCwd: root, mixedModules: true });
for (const name of traced.fileList) {
  if (name.startsWith('.next/news-ci/') || name.endsWith('.map')) continue;
  if (!name.startsWith('node_modules/')) throw Error('Unexpected collector dependency');
  const src = path.resolve(root, name);
  if (!src.startsWith(root + '/')) throw Error('Escaped runtime dependency');
  if (!(await fs.stat(src)).isFile()) continue;
  const dest = path.join(out, name);
  await fs.mkdir(path.dirname(dest), { recursive: true });
  await fs.copyFile(src, dest);
}
for (const name of ['node_modules/.prisma/client', 'node_modules/@prisma/client', 'node_modules/@prisma/adapter-pg']) {
  await fs.cp(path.join(root, name), path.join(out, name), { recursive: true, dereference: true });
}
// Production output contains neither build settings files nor writable caches.
const files = {};
async function walk(dir) {
  for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
    const absolute = path.join(dir, entry.name);
    const relative = path.relative(out, absolute).split(path.sep).join('/');
    if (entry.name.startsWith('.env') || ['.git', '.ssh', '.npmrc', '.next-cache'].includes(entry.name) || relative === '.next/cache') {
      await fs.rm(absolute, { recursive: true, force: true }); continue;
    }
    if (entry.isSymbolicLink()) throw Error('Unexpected runtime symlink');
    if (entry.isDirectory()) await walk(absolute);
    else if (entry.isFile()) files[relative] = createHash('sha256').update(await fs.readFile(absolute)).digest('hex');
    else throw Error('Unsupported runtime entry');
  }
}
await walk(out);
await fs.writeFile(path.join(out, 'deploy-manifest.json'), JSON.stringify({ schema: 1, revision, files }));
console.log(JSON.stringify({ revision, runtime_files: Object.keys(files).length, credentials_included: false, collector_executed: false }));

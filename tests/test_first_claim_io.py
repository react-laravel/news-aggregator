"""Real temporary archives, stable locks and root-claim copies; host calls mocked."""
import hashlib
import importlib.util
import io
import json
import os
import shutil
from pathlib import Path
import tarfile
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('first_claim',ROOT/'deployment/bootstrap-old-news.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)

class FirstClaimIO(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.control=self.root/'root-control';self.control.mkdir()
        self.state=self.root/'deploy-state';self.state.mkdir();(self.state/'incoming').mkdir()
        self.release=self.root/'app/releases';self.release.mkdir(parents=True)
        (self.root/'app/shared/cache').mkdir(parents=True)
        (self.release/B.LEGACY).mkdir();(self.release/'current').symlink_to(B.LEGACY)
        (self.root/'app/current').symlink_to('releases/current')
        self.revision='b'*40;self.nonce='c'*32;self.archive=self.state/'incoming'/(self.revision+'.tar.gz')
        files={name:b'offline fixture' for name in B.P.REQUIRED}
        manifest={'schema':1,'revision':self.revision,'files':{name:hashlib.sha256(value).hexdigest() for name,value in files.items()}}
        with tarfile.open(self.archive,'w:gz') as tar:
            for name,value in {**files,'deploy-manifest.json':json.dumps(manifest).encode()}.items():
                item=tarfile.TarInfo(name);item.size=len(value);tar.addfile(item,io.BytesIO(value))
        expected,total=B.P.inspect_archive(self.archive,self.revision)
        self.ready={'schema':2,'revision':self.revision,'legacy':B.LEGACY,'nonce':self.nonce,'archive_bytes':self.archive.stat().st_size,'archive_sha256':hashlib.sha256(self.archive.read_bytes()).hexdigest(),'expanded_bytes':total,'expires_at':time.time()+1700,'files':expected}
        (self.state/'first-publish-ready.json').write_text(json.dumps(self.ready))
        self.patchers=[mock.patch.object(B,n,v) for n,v in {'CONTROL':self.control,'FIRST_STATE':self.control/'first-state.json','DEPLOY_STATE':self.state}.items()]
        self.patchers += [mock.patch.object(B.P,n,v) for n,v in {'APP':self.root/'app','RELEASES':self.release,'STATE':self.state,'INCOMING':self.state/'incoming'}.items()]
        self.patchers += [mock.patch.object(B,'root_preflight'),mock.patch.object(B,'run',return_value='active'),mock.patch.object(B.pwd,'getpwnam',return_value=types.SimpleNamespace(pw_uid=os.geteuid()))]
        for p in self.patchers:p.start()
    def tearDown(self):
        for p in reversed(self.patchers):p.stop()
        self.tmp.cleanup()
    def test_root_claim_copies_verified_package_before_committing_and_survives_upload_deletion(self):
        state=B.claim(self.revision,self.nonce)
        canonical=Path(state['claim_root'])/'runtime.tar.gz'
        self.assertFalse(self.archive.exists());self.assertTrue(canonical.exists())
        self.assertEqual(canonical.stat().st_mode&0o777,0o400)
        self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(),self.ready['archive_sha256'])
        self.assertTrue((canonical.parent/'runtime/ingest.cjs').is_file())
        self.assertEqual(json.loads((self.control/'first-state.json').read_text())['phase'],'claimed')
        # The only deploy-side path can be replaced after adoption without
        # changing the independent, immutable canonical package.
        self.archive.write_bytes(b'replacement upload')
        self.assertEqual(hashlib.sha256(canonical.read_bytes()).hexdigest(),self.ready['archive_sha256'])
        with mock.patch.object(B,'read_json',side_effect=lambda path,**kw:json.loads(Path(path).read_text())):
            same=B.claim(self.revision,self.nonce)
        self.assertEqual(same['nonce'],self.nonce)
    def test_expired_stale_nonce_or_removed_candidate_never_claims_or_changes_legacy(self):
        for kind in ['expired','nonce','removed','replacement']:
            with self.subTest(kind=kind):
                record=dict(self.ready)
                if kind=='expired':record['expires_at']=time.time()-1
                if kind=='nonce':record['nonce']='d'*32
                (self.state/'first-publish-ready.json').write_text(json.dumps(record))
                original=self.archive.read_bytes() if self.archive.exists() else None
                if kind=='removed':self.archive.unlink()
                if kind=='replacement':self.archive.write_bytes(b'wrong package')
                with self.assertRaises((B.ProtocolError,FileNotFoundError)):
                    B.claim(self.revision,self.nonce)
                self.assertFalse((self.control/'first-state.json').exists())
                self.assertEqual(os.readlink(self.release/'current'),B.LEGACY)
                if original is not None:self.archive.write_bytes(original)
    def test_root_state_rejects_different_nonce_without_pid_identity(self):
        state=B.claim(self.revision,self.nonce)
        with mock.patch.object(B,'read_json',side_effect=lambda path,**kw:json.loads(Path(path).read_text())):
            with self.assertRaises(B.ProtocolError):B.claim(self.revision,'e'*32)
        self.assertNotIn('pid',state);self.assertEqual(state['nonce'],self.nonce)
    def test_complete_orphan_can_be_adopted_after_state_commit_crash_without_upload(self):
        original_atomic=B.atomic_json
        def interrupted(path,value,*args,**kwargs):
            if Path(path)==self.control/'first-state.json':raise SystemExit(91)
            return original_atomic(path,value,*args,**kwargs)
        with mock.patch.object(B,'atomic_json',side_effect=interrupted):
            with self.assertRaises(SystemExit):B.claim(self.revision,self.nonce)
        canonical=self.control/'claims'/(self.revision+'-'+self.nonce)
        self.assertTrue((canonical/'request.json').is_file());self.assertFalse((self.control/'first-state.json').exists())
        self.archive.unlink();(self.state/'first-publish-ready.json').unlink()
        with mock.patch.object(B,'read_json',side_effect=lambda path,**kw:json.loads(Path(path).read_text())),mock.patch.object(B,'protected_file'):
            state=B.claim(self.revision,self.nonce)
        self.assertEqual(state['phase'],'claimed');self.assertEqual(state['nonce'],self.nonce)
        self.assertEqual(os.readlink(self.release/'current'),B.LEGACY)
    def test_recovery_expansion_crash_does_not_make_resume_permanently_fail(self):
        state=B.claim(self.revision,self.nonce);host=B.Host()
        host.place_release(state)
        shutil.rmtree(self.release/self.revision)
        original=B.P.extract_archive
        def interrupted(archive,stage,expected):
            (stage/'partial').write_text('incomplete own recovery')
            raise SystemExit(92)
        with mock.patch.object(B.P,'extract_archive',side_effect=interrupted):
            with self.assertRaises(SystemExit):host.place_release(state)
        self.assertTrue((Path(state['claim_root'])/'.recover-runtime/partial').exists())
        host.place_release(state)
        self.assertTrue(host.verify_runtime(self.release/self.revision,state))
        self.assertFalse((Path(state['claim_root'])/'.recover-runtime').exists())
    def test_changed_manifest_is_rejected_before_durable_claim(self):
        self.ready['files']['ingest.cjs']='0'*64
        (self.state/'first-publish-ready.json').write_text(json.dumps(self.ready))
        with self.assertRaises(B.ProtocolError):B.claim(self.revision,self.nonce)
        self.assertFalse((self.control/'first-state.json').exists())
        self.assertEqual(os.readlink(self.release/'current'),B.LEGACY)

if __name__=='__main__':unittest.main()

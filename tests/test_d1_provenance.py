"""Do not admit unknown model changes or a default backend into the v1 study."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from wafer_sim.experiments.d1_provenance import verify_saved_sources, backend_identity
from wafer_sim.io import digest


class D1ProvenanceTests(unittest.TestCase):
    def test_archived_source_bridge_is_bounded_and_checks_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp)
            subprocess.run(['git','init','-q',str(repo)],check=True)
            allowed='src/wafer_sim/adapters/wafer_machine.py'
            model='src/wafer_sim/adapters/shared_spatial_service.py'
            for name in (allowed,model):
                path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('original')
            subprocess.run(['git','-C',str(repo),'add','.'],check=True)
            subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                'commit','-qm','baseline'],check=True)
            start=dict(source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
                       source_hashes={name:digest(repo/name) for name in (allowed,model)})
            self.assertEqual(verify_saved_sources(repo,start),{})
            (repo/allowed).write_text('reviewed validator/public interface')
            self.assertEqual(set(verify_saved_sources(repo,start)),{allowed})
            wrong=dict(start,source_hashes={**start['source_hashes'],allowed:'bad'})
            with self.assertRaisesRegex(ValueError,'Archived'):verify_saved_sources(repo,wrong)
            (repo/model).write_text('changed sharing algorithm')
            with self.assertRaisesRegex(ValueError,'unreviewed'):verify_saved_sources(repo,start)

    def test_explicit_model_and_backend_are_required(self):
        names={'D0':'independent_spatial_service','D1':'shared_spatial_service','S':'booksim'}
        for model,backend in names.items():
            expected=backend_identity(model,{'model':model},{'network_backend':backend})
            self.assertEqual(expected['transaction_policy'],'whole')
            with self.assertRaises(ValueError):backend_identity(model,{'model':model},{})
            with self.assertRaises(ValueError):backend_identity(model,{'model':model},{'network_backend':'default'})
        with self.assertRaises(ValueError):backend_identity('D1',{'model':'S'},{'network_backend':'shared_spatial_service'})

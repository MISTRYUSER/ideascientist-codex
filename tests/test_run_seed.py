import importlib.util
import tempfile
import unittest
from pathlib import Path


class SeedTests(unittest.TestCase):
    def test_seed_copies_artifacts_without_overwriting_original_logs(self):
        spec = importlib.util.spec_from_file_location('run_script', Path(__file__).resolve().parents[1]/'scripts/run_ideation.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            source, destination = Path(d)/'source', Path(d)/'new'
            (source/'outputs/papers').mkdir(parents=True)
            (source/'logs').mkdir()
            (source/'outputs/gaps.md').write_text('existing gap')
            (source/'outputs/papers/42.md').write_text('existing digest')
            (source/'logs/old.json').write_text('preserve')
            module.seed_outputs(source, destination)
            self.assertEqual((destination/'outputs/gaps.md').read_text(), 'existing gap')
            self.assertEqual((destination/'outputs/papers/42.md').read_text(), 'existing digest')
            self.assertEqual((source/'logs/old.json').read_text(), 'preserve')
            self.assertFalse((destination/'logs/old.json').exists())
            with self.assertRaises(ValueError):
                module.seed_outputs(source, source)


if __name__ == '__main__':
    unittest.main()

"""Executable discovery tests do not install software or launch services."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('runtime_tools',Path(__file__).resolve().parents[1]/'scripts/runtime_tools.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)


class RuntimeToolsTests(unittest.TestCase):
    def test_node_discovered_from_path(self):
        with patch.dict(os.environ,{},clear=True),patch.object(runtime.shutil,'which',return_value='/tools/node') as which:
            self.assertEqual(runtime.find_node(),'/tools/node');which.assert_called_once_with('node')

    def test_configured_node_override_is_used_and_missing_node_fails(self):
        with patch.dict(os.environ,{'GLUCOTWIN_NODE':'custom-node'}),patch.object(runtime.shutil,'which',return_value='/custom/node') as which:
            self.assertEqual(runtime.find_node(),'/custom/node');which.assert_called_once_with('custom-node')
        with patch.object(runtime.shutil,'which',return_value=None):
            with self.assertRaisesRegex(SystemExit,'PATH or set GLUCOTWIN_NODE'):runtime.find_node()

    def test_virtual_environment_interpreter_is_platform_aware(self):
        self.assertEqual(runtime.venv_python('fixture'),Path('fixture')/('Scripts/python.exe' if os.name=='nt' else 'bin/python'))

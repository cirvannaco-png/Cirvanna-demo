import subprocess
from pathlib import Path
import pytest
from tools.model_training.provenance import require_clean_source_revision

def git(root:Path,*args):
    return subprocess.check_output(["git",*args],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()

def test_requires_a_clean_committed_source_tree(tmp_path):
    git(tmp_path,"init","-q")
    git(tmp_path,"config","user.email","cvi-test@example.invalid")
    git(tmp_path,"config","user.name","CVI Test")
    source=tmp_path/"model.py"; source.write_text("MODEL_VERSION = 1\n")
    git(tmp_path,"add","model.py")
    git(tmp_path,"commit","-m","initial model")
    revision=require_clean_source_revision(tmp_path)
    assert len(revision)==40
    source.write_text("MODEL_VERSION = 2\n")
    with pytest.raises(RuntimeError,match="clean source tree"):
        require_clean_source_revision(tmp_path)

def test_rejects_non_git_training_directory(tmp_path):
    with pytest.raises(RuntimeError,match="Git checkout"):
        require_clean_source_revision(tmp_path)

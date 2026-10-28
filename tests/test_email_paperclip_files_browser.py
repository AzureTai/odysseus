"""The native FileList must survive resetting the compose file input."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.helpers.document_source import function_body


@pytest.mark.parametrize("selections", [[["one.txt"]], [["one.txt", "two.csv"]], [["one.txt"], ["one.txt"]], [[]]])
def test_compose_file_selection_survives_reset(tmp_path, selections):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    for name, content in [("one.txt", "Synthetic attachment one\n"), ("two.csv", 'name,value\n"fixture",2\n')]:
        (tmp_path / name).write_text(content, encoding="utf-8")
    script = r"""
const fs=require('node:fs'),assert=require('node:assert/strict');
let chromium;try{({chromium}=require('playwright'));}catch(e){if(e.code==='MODULE_NOT_FOUND')process.exit(77);throw e;}
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<input type="file" multiple aria-label="Compose attachments">');
  await page.addScriptTag({content:`
    window.uploads=[];window.finished=0;
    async function _uploadComposeFiles(files){
      for(const file of files)window.uploads.push({name:file.name,text:await file.text()});
    }
    __HANDLER__
    document.querySelector('input').addEventListener('change',async event=>{
      await _handleAttachUpload(event);window.finished++;
    });
  `});
  const selections=JSON.parse(process.argv[1]),root=process.argv[2],expected=[];
  for(const [index,names] of selections.entries()){
   await page.getByLabel('Compose attachments').setInputFiles(names.map(name=>root+'/'+name));
   await page.waitForFunction(n=>window.finished===n,index+1);
   expected.push(...names.map(name=>({name,text:fs.readFileSync(root+'/'+name,'utf8')})));
   assert.deepEqual(await page.evaluate(()=>window.uploads),expected);
   assert.equal(await page.getByLabel('Compose attachments').inputValue(),'');
   assert.equal(await page.getByLabel('Compose attachments').evaluate(el=>el.files.length),0);
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({files:expected.length}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
""".replace("__HANDLER__", function_body("_handleAttachUpload"))
    result = subprocess.run(["node", "-e", script, json.dumps(selections), str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True,
                            text=True, timeout=30)
    if result.returncode == 77:
        pytest.skip("playwright not installed")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["files"] == sum(map(len, selections))

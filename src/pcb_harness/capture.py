"""Opt-in macOS capture of one bound PCB Editor window; never desktop capture."""
from pathlib import Path
import hashlib
import io
import json
import re
import subprocess
import sys
from PIL import Image
from .contracts import HarnessError


def instance_pid(socket):
    match=re.fullmatch(r'ipc://.+/api-([1-9][0-9]*)\.sock',socket)
    if not match:raise HarnessError('CAPTURE_IDENTITY_REQUIRED','capture requires explicit api-<PID>.sock of the bound PCB Editor')
    return int(match.group(1))


def select_editor_window(windows,pid,project_stem):
    titles={f'{project_stem} — PCB Editor',f'*{project_stem} — PCB Editor'}
    candidates=[w for w in windows if w.get('kCGWindowOwnerPID')==pid and
        w.get('kCGWindowOwnerName') in ('pcbnew','PCB Editor') and w.get('kCGWindowName') in titles and
        w.get('kCGWindowLayer')==0 and isinstance(w.get('kCGWindowNumber'),int)]
    if len(candidates)!=1:raise HarnessError('CAPTURE_WINDOW_UNAVAILABLE','expected one bound PCB Editor board window')
    return candidates[0]


def load_quartz():
    if sys.platform!='darwin':raise HarnessError('CAPTURE_UNSUPPORTED_PLATFORM','editor capture is currently macOS-only')
    try:import Quartz
    except ImportError as error:raise HarnessError('CAPTURE_DEPENDENCY_MISSING','install the capture extra on macOS') from error
    return Quartz


def capture_editor(project,socket,revision,output):
    pid=instance_pid(socket);quartz=load_quartz()
    if not quartz.CGPreflightScreenCaptureAccess():
        raise HarnessError('SCREEN_CAPTURE_PERMISSION_REQUIRED',
            'macOS Screen Recording permission is required; enable it for the host/terminal yourself. No permission prompt or capture was attempted.')
    def windows():return quartz.CGWindowListCopyWindowInfo(quartz.kCGWindowListOptionOnScreenOnly,quartz.kCGNullWindowID) or []
    window=select_editor_window(windows(),pid,Path(project).stem)
    output=Path(output);output.mkdir(parents=True,exist_ok=True);path=output/'editor.png'
    if path.exists():raise HarnessError('OUTPUT_EXISTS','refusing to reuse prior screenshot')
    command=['/usr/sbin/screencapture','-x','-o','-l',str(window['kCGWindowNumber']),'-t','png',str(path.resolve())]
    try:result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    except (OSError,subprocess.TimeoutExpired) as error:raise HarnessError('CAPTURE_FAILED',str(error)) from error
    if result.returncode or not path.is_file():raise HarnessError('CAPTURE_FAILED','bound window capture did not return a PNG')
    again=select_editor_window(windows(),pid,Path(project).stem)
    if again['kCGWindowNumber']!=window['kCGWindowNumber']:raise HarnessError('CAPTURE_WINDOW_CHANGED','window identity changed during capture')
    if path.stat().st_size>20*1024*1024:raise HarnessError('CAPTURE_FAILED','capture exceeds file budget')
    try:
        image=Image.open(path)
        if image.format!='PNG' or image.width*image.height>20_000_000:raise HarnessError('CAPTURE_FAILED','invalid/unbounded PNG')
        image=image.convert('RGB');original_size=list(image.size)
        image.thumbnail((2048,2048))
        data=io.BytesIO();image.save(data,format='PNG');png=data.getvalue()
    except (OSError,ValueError) as error:raise HarnessError('CAPTURE_FAILED','invalid screenshot image') from error
    if len(png)>6*1024*1024:raise HarnessError('CAPTURE_FAILED','PNG exceeds MCP image budget')
    path.write_bytes(png)
    metadata={'ok':True,'source':'PCB Editor window capture','revision':revision,'test_only':False,
        'window':{'id':window['kCGWindowNumber'],'pid':pid,'title':window['kCGWindowName'],
            'bounds_points':dict(window.get('kCGWindowBounds',{}))},
        'board_coordinate_mapping':None,'release_verified':False,
        'image':{'path':str(path.resolve()),'mime_type':'image/png','width_px':image.width,'height_px':image.height,
            'original_size_px':original_size,'sha256':hashlib.sha256(png).hexdigest()}}
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    return {**metadata,'_image_bytes':png}

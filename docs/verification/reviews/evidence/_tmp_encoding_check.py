import subprocess, pathlib
markers = ['\u6d93','\u95ab','\u93cd','\u9359','\u951f']  # 涓 閫 鏍 鍙 锟
paths = ['test-platform/frontend/src/styles/theme.scss','test-platform/frontend/src/styles/index.scss']
for p in paths:
    b = subprocess.check_output(['git','-C',r'D:\MCTEST','show','HEAD:'+p])
    head = b.split(b'\n',1)[0]
    print('==', p)
    print('  HEAD first-line hex:', head[:60].hex())
    print('  HEAD utf8  :', ascii(head.decode('utf-8','replace')))
    try:
        print('  HEAD gbk   :', ascii(head.decode('gbk','replace')))
    except Exception as e:
        print('  HEAD gbk   : FAIL', e)
    htxt = b.decode('utf-8','replace')
    print('  HEAD markers present:', [m for m in markers if m in htxt])
    cur = pathlib.Path(r'D:\MCTEST') / p
    cb = cur.read_bytes()
    chead = cb.split(b'\n',1)[0]
    ctxt = cb.decode('utf-8','replace')
    print('  WORK first-line hex:', chead[:60].hex())
    print('  WORK utf8  :', ascii(chead.decode('utf-8','replace')))
    print('  WORK markers present:', [m for m in markers if m in ctxt])
    print('  WORK has U+FFFD:', '\ufffd' in ctxt)

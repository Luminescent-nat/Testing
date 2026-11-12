import pathlib
p = pathlib.Path(r'D:\MCTEST\.gitattributes')
b = p.read_bytes()
print('bytes:', b[:80].hex())
print('ascii-utf8:', ascii(b.decode('utf-8','replace')))
print('has FFFD:', '\ufffd' in b.decode('utf-8','replace'))

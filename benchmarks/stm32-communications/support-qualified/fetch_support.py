import concurrent.futures,hashlib,json,pathlib,subprocess
root=pathlib.Path('runs/m4/support-qualification-2026-10-10/sources');root.mkdir(parents=True,exist_ok=True)
urls={
'resistor':'https://www.vishay.com/docs/20035/dcrcwe3.pdf',
'abm3b':'https://abracon.com/Resonators/abm3b.pdf',
'abm8':'https://abracon.com/Resonators/abm8.pdf',
'coilcraft':'https://www.coilcraft.com/getmedia/6adcb47d-8b55-416c-976e-1e22e0d2848c/xal4000.pdf',
'usb-drawing':'https://gct.co/files/drawings/usb4105.pdf',
'usb-spec':'https://gct.co/files/specs/usb4105-spec.pdf',
'pmv48xp':'https://assets.nexperia.com/documents/data-sheet/PMV48XP.pdf',
'bss84':'https://assets.nexperia.com/documents/data-sheet/BSS84.pdf',
'mmbt3904':'https://assets.nexperia.com/documents/data-sheet/MMBT3904.pdf',
'usblc6':'https://www.st.com/resource/en/datasheet/usblc6-2.pdf',
'nup2105':'https://www.onsemi.com/pdf/datasheet/nup2105l-d.pdf',
'sm712':'https://www.littelfuse.com/assetdocs/tvs-diode-array-spa-sm712-datasheet?assetguid=8313a28c-8802-4d47-a2a7-e30b5b1f67d8',
'ftsh':'https://suddendocs.samtec.com/prints/ftsh-1xx-xx-xxx-dv-xxx-xxx-mkt.pdf',
'header':'https://suddendocs.samtec.com/prints/tsw-xxx-xx-xxx-x-xx-xxx-mkt.pdf',
'female-header':'https://suddendocs.samtec.com/prints/ssw-xxx-xx-xxx-xx-xxx-xx-mkt.pdf',
'keyed-cable':'https://suddendocs.samtec.com/catalog_english/ffsd.pdf',
'cog-pump':'https://product.tdk.cn/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c3216c0g1h104j160aa.pdf',
'cap22u':'https://product.tdk.cn/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c3225x7r1c226k250ac.pdf',
'cap10u':'https://product.tdk.cn/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c3225x7r1e106k250ac.pdf',
'cap100n':'https://product.tdk.cn/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c1608x7r1h104k080aa.pdf',
'cap1u':'https://product.tdk.cn/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c1608x7r1c105k080ac.pdf',
'cap47u':'https://product.tdk.cn/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c2012x7r1c475k125ab.pdf',
'cap27p':'https://product.tdk.cn/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c1608c0g1h270j080aa.pdf',
'cap30p':'https://product.tdk.cn/system/files/dam/doc/product/capacitor/ceramic/mlcc/charasheet/c1608c0g1h300j080aa.pdf',
'usb-tvs-new':'https://assets.nexperia.com/documents/data-sheet/PESD2USB5UX-T.pdf',
'can-tvs-new':'https://assets.nexperia.com/documents/data-sheet/PESD2CANFD24V-T.pdf',
'reset':'https://www.ckswitches.com/media/1471/pts645.pdf',
'testpoint':'https://www.keyelco.com/pdfs/p33.pdf',
'shunt':'https://suddendocs.samtec.com/prints/snt-100-xx-x-x-mkt.pdf',
'header-land':'https://suddendocs.samtec.com/prints/tsw-xxx-xx-x-x-xx-xxx-footprint.pdf',
'header-catalog':'https://suddendocs.samtec.com/catalog_english/tsw_th.pdf',
'usb-or':'https://www.ti.com/lit/ds/symlink/sn74lvc1g32.pdf',
'header-current':'https://www.ti.com/lit/ds/symlink/tps22946.pdf',
'kemet-cog':'https://content.kemet.com/datasheets/KEM_C1003_C0G_SMD.pdf',
'kemet27p':'https://search.kemet.com/component-documentation/download/specsheet/C0603C270J5GACTU',
'kemet30p':'https://search.kemet.com/component-documentation/download/specsheet/C0603C300J5GACTU',
'resistor-hp':'https://www.vishay.com/docs/20043/crcwhpe3.pdf',
'lm66100':'https://www.ti.com/lit/ds/symlink/lm66100.pdf',
'tmux1574':'https://www.ti.com/lit/ds/symlink/tmux1574.pdf',
'lvc125':'https://www.ti.com/lit/ds/symlink/sn74lvc125a.pdf',
'lvc1g125':'https://www.ti.com/lit/ds/symlink/sn74lvc1g125.pdf',
'i2c-buffer':'https://www.ti.com/lit/ds/symlink/tca9511a.pdf',
'input-protection':'https://www.ti.com/lit/ds/symlink/tps25947.pdf',
}
def one(t):
 k,u=t;p=root/(k+'.pdf')
 if p.exists():
  b=p.read_bytes();return {'id':k,'url':u,'retrieved_url':u,'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'status':'retrieved','rights':'Publisher copyright retained; reference evidence only, no redistribution license inferred.'}
 try:
  run=subprocess.run(['curl','--http1.1','--retry','2','--retry-all-errors','-f','-L','--max-time','25','-A','Mozilla/5.0',u],capture_output=True,check=True)
  b=run.stdout;actual=u
  if b[:4]!=b'%PDF': raise ValueError('not PDF '+repr(b[:100]))
  p.write_bytes(b)
  return {'id':k,'url':u,'retrieved_url':actual,'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'status':'retrieved','rights':'Publisher copyright retained; reference evidence only, no redistribution license inferred.'}
 except Exception as e:return {'id':k,'url':u,'status':'unavailable','error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:docs=list(pool.map(one,urls.items()))
pathlib.Path('benchmarks/stm32-communications/support-qualified/sources.json').write_text(json.dumps({'documents':docs},indent=2)+'\n')
for d in docs:print(d['id'],d['status'],d.get('bytes',d.get('error')))

import pathlib,json
root=pathlib.Path('candidate');meta=json.loads((root/'meta.json').read_text())
for group,filename in [('native','result.json'),('select-ui','select-ui-result.json')]:
 rows=[json.loads(p.read_text()) for p in pathlib.Path('verified-native').glob('*/'+filename)]
 assert len(rows)==3 and {r['api'] for r in rows}=={'30','35','36'}
 assert all(r['allPassed'] and r['apkSha256']==meta['sha256'] for r in rows)
 (root/(group+'-results.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
notes='Світло '+meta['version']+' / '+str(meta['versionCode'])+'\n\n'+meta['notes']+'\n\nТа сама підписана APK перевірена на API30/35/36: оновлення з76 зі збереженням адрес, ручна черга та перезапуск, чистий запуск; п’ять полів вибору адреси з довгими назвами й системним шрифтом1/1.5. За пікселями знімків перевірено напрямок шеврона вниз, його положення праворуч і відсутність накладання тексту.\n\n224 Node-тести й96 сценаріїв React виконані окремо. Повна матриця9 груп попереднього випуску76 залишається в його звітах; незмінені офлайн- та джерельні модулі повторно нативно не тестувалися. Тестові дані поза APK. Вихідний коміт: '+meta['sourceCommit']+'.\n'
(root/'VERIFIED-NOTES.md').write_text(notes)

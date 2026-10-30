import pathlib,json
root=pathlib.Path('candidate');meta=json.loads((root/'meta.json').read_text())
for group,filename in [('native','result.json'),('navigation-ui','navigation-ui-result.json')]:
 rows=[json.loads(p.read_text()) for p in pathlib.Path('verified-native').glob('*/'+filename)]
 assert len(rows)==3 and {r['api'] for r in rows}=={'30','35','36'}
 assert all(r['allPassed'] and r['apkSha256']==meta['sha256'] for r in rows)
 (root/(group+'-results.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
notes='Світло '+meta['version']+' / '+str(meta['versionCode'])+'\n\n'+meta['notes']+'\n\nТа сама підписана APK пройшла оновлення з опублікованої74 зі збереженням адрес, ручну правку черги та перезапуск, навігацію, прості шапки «Налаштування»/«Мої адреси» з дією «Закрити», повернення до графіка, вибір адреси, великий системний шрифт, порожній список і додавання адреси на API30/35/36. Дані QA поза APK. Це перевірка шапок/навігації на емуляторах, не новий аудит живого покриття чи фізичного телефона.\n\nОкремо пройдено223 Node-тести,93 реальних сценарії React,11 сценаріїв оновлення,5 перевірок сповіщень,5 фонових і3 браузерні перевірки. Повний нативний аудит офлайн/джерел виконаний для74; у75 ці модулі не змінені. Вихідний коміт: '+meta['sourceCommit']+'.\n'
(root/'VERIFIED-NOTES.md').write_text(notes)

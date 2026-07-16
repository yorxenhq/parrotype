# Language gate results

Engine: large-v3-turbo @ cuda (float16), production decode params, language forced per case. Test speech: edge-tts neural voices (dev-time tool). Gate: keyword recall >= 80%.

| Language | Keyword recall | Verdict | Transcript |
|---|---|---|---|
| en | 100% | PASS | Open the settings window, check the latency table and restart the local server before the  |
| ru | 100% | PASS | Открой окно настроек, проверь таблицу задержек и перезапусти локальный сервер перед совеща |
| es | 100% | PASS | Abre la ventana de configuración, revisa la tabla de latencia y reinicia el servidor local |
| de | 83% | PASS | Öffne das Einstellungsfenster, prüfe die Lattens-Tabelle und starte den lokalen Server vor |
| fr | 100% | PASS | Ouvre la fenêtre des paramètres, vérifie le tableau de latence et redémarre le serveur loc |
| it | 100% | PASS | Apri la finestra delle impostazioni, controlla la tabella della latenza e riavvia il serve |
| pt | 100% | PASS | Abra a janela de Configurações, verifique a tabela de latência e reinicie o servidor local |
| pl | 100% | PASS | Otwórz okno ustawień, sprawdź tabelę opóźnień i zrestartuj lokalny serwer przed spotkaniem |
| uk | 100% | PASS | Відкрий вікно налаштувань, перевір таблицю затримок і перезапусти локальний сервер перед н |
| nl | 100% | PASS | Open het instellingenvenster, controleer de latentietabel en herstart de lokale server voo |
| tr | 100% | PASS | Ayarlar penceresini aç, gecikme tablosunu kontrol et ve toplantıdan önce yerel sunucuyu ye |
| ja | 100% | PASS | 設定ウィンドウを開いて、遅延テーブルを確認し、会議の前にロカルサーバーを再起動してください。 |
| ko | 100% | PASS | 설정 창을 열고 지연 시간 테이블을 확인한 다음 회의 전에 로컬 서버를 다시 시작하세요. |
| zh | 100% | PASS | 打开设置窗口,检查延迟表格,并在会议之前重启本地服务器。 |

Passed (14): en, ru, es, de, fr, it, pt, pl, uk, nl, tr, ja, ko, zh
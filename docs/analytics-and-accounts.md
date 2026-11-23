# TransferLab — аналитика посещений и регистрация

Реализация: scripts/account_build.py, assets/account.js, assets/account.css, supabase/player_history.sql.

## Посещения без регистрации — Cloudflare Web Analytics

1. Откройте Cloudflare Web Analytics: https://dash.cloudflare.com/
2. Добавьте сайт https://gosha-tech.github.io/transferlab/ и скопируйте Web Analytics Site Token из ручного JS-snippet.
3. В репозитории GitHub откройте Settings → Secrets and variables → Actions → Variables.
4. Создайте переменную **TRANSFERLAB_CLOUDFLARE_WEB_ANALYTICS_TOKEN** со значением токена из Cloudflare (32 шестнадцатеричных символа).
5. В GitHub Actions выполните Build and publish TransferLab → Run workflow.
6. Статистику смотрите в Cloudflare: Visits, Page Views, источники трафика и тенденции.

Cloudflare Web Analytics не требует переносить домен на Cloudflare и подходит для GitHub Pages. Без токена скрипт аналитики не запускается, а прошлые посещения задним числом не считаются. Число просмотров и число уникальных людей — разные метрики.

## Аккаунты и история — Supabase Auth

1. Создайте проект: https://supabase.com/dashboard
2. В Supabase SQL Editor выполните файл **supabase/player_history.sql** из репозитория. Он включает Row Level Security: каждый вошедший пользователь имеет доступ только к своим данным.
3. Откройте Authentication → URL Configuration и укажите Site URL и Redirect URL: **https://gosha-tech.github.io/transferlab/**. Убедитесь, что email-вход включён.
4. В GitHub → Settings → Secrets and variables → Actions → Variables создайте:
   - **TRANSFERLAB_SUPABASE_URL** = HTTPS-адрес проекта Supabase;
   - **TRANSFERLAB_SUPABASE_PUBLISHABLE_KEY** = публичный publishable key (или legacy anon key).
5. Запустите обычный workflow публикации сайта GitHub Pages.
6. Проверьте регистрацию тестовым email. Для реального роста аудитории проверьте email-квоты и настройте SMTP.

**Никогда не публикуйте Supabase secret key или service_role key в статическом сайте.** Скрипт сборки их отвергает. Без Supabase ключей форма входа скрывается, гостевая история остаётся доступна.

В Supabase Dashboard → Authentication → Users видно количество зарегистрированных аккаунтов. Это отдельная метрика от посещений Cloudflare.

## Что увидит пользователь

- Кнопка «История» постоянно отображается в боковом меню.
- Без регистрации сохраняются до 60 последних просмотренных профилей на устройстве (localStorage).
- После входа по email ссылка с подтверждением открывает страницу сайта; локальная история переносится в личную базу и синхронизируется между устройствами.
- Кнопка «Очистить» удаляет историю локально и, если пользователь вошёл, из его базы.
- Выход удаляет с устройства локальную копию истории аккаунта.
- История не влияет на спортивные индексы и Hidden Gems.

## Безопасность и публикация

Перед включением регистрации убедитесь, что два разных тестовых аккаунта не видят историю друг друга; добавьте политику конфиденциальности и процедуру удаления пользовательских данных. Email адреса не отправляются в Cloudflare или в публичный профиль футболиста.

Официальные инструкции:
- https://developers.cloudflare.com/web-analytics/get-started/
- https://supabase.com/docs/reference/javascript/auth-signinwithotp
- https://supabase.com/docs/guides/database/postgres/row-level-security

# Деплой на VPS: гайд для опытной проверки (постоянный хостинг)

Quick Tunnel с ноутбука — только демо. Для постоянной работы нужен VPS с фиксированным адресом.

## Где размещать

**Рекомендация: российский провайдер** (клиентам из РФ сайты Cloudflare замедляют с июня 2025):

- Timeweb Cloud — есть локации в РФ и Казахстане, оплата картой РФ, от 300 ₽/мес
- Selectel, FirstVDS, Beget, AdminVPS — то же самое
- Yandex Cloud — если нужна юридическая чистота для вуза

Минимальные требования: 1 vCPU, 1 ГБ RAM, 10 ГБ SSD. Ubuntu 22.04/24.04.

> Если OpenRouter плохо отвечает с РФ-IP провайдера, задайте в `.env`
> `HTTPS_PROXY=http://user:pass@proxy:port` — requests подхватит автоматически.

## Установка на сервер (пошагово)

```bash
# 1. Пользователь и каталог
sudo useradd -m -s /bin/bash trainer
sudo mkdir -p /opt/trainer && sudo chown trainer /opt/trainer

# 2. Файлы проекта: scp/rsync с ноутбука
#    на ноутбуке (в папке проекта):
scp -r app.py run_production.py requirements.txt trainer templates static data deploy trainer@IP:/opt/trainer/

# 3. Зависимости
cd /opt/trainer
sudo -u trainer python3 -m venv .venv
sudo -u trainer .venv/bin/pip install -r requirements.txt gunicorn

# 4. Окружение
cp .env.example .env
nano .env   # SECRET_KEY (случайная строка), OPENROUTER_API_KEY, TEACHER_PASSWORD
chmod 600 .env

# 5. Сервис
sudo cp deploy/trainer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trainer
sudo systemctl status trainer

# 6. nginx
sudo apt install -y nginx
sudo cp deploy/nginx.conf /etc/nginx/sites-available/trainer
#    замените trainer.example.ru на домен или IP
sudo ln -s /etc/nginx/sites-available/trainer /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 7. Брандмауэр
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

После этого сайт: `http://IP_СЕРВЕРА/`, кабинет: `http://IP_СЕРВЕРА/teacher/login`.

## HTTPS (по желанию, с доменом)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d trainer.example.ru
```

## Бэкапы на сервере

База — `data/trainer.db`. Ежедневный крон:

```bash
sudo crontab -u trainer -e
# строка ниже — копия в data/backups, хранится 14 дней
0 3 * * * cd /opt/trainer && .venv/bin/python -c "import sqlite3,shutil,datetime,os; d='data/backups'; os.makedirs(d,exist_ok=True); t=f'{d}/trainer_{datetime.date.today()}.db'; s=sqlite3.connect('data/trainer.db'); x=sqlite3.connect(t); s.backup(x); x.close(); s.close(); files=sorted([f'{d}/{f}' for f in os.listdir(d)],reverse=True); [os.remove(f) for f in files[14:]]"
```

Плюс раз в неделю скопируйте `data/backouts` на ноутбук или в объектное хранилище.

## Обновление

```bash
cd /opt/trainer
scp -r app.py trainer templates static data/word_lists trainer@IP:/opt/trainer/
sudo systemctl restart trainer
```

## Проверка после запуска

1. Откройте `http://IP/` — лендинг.
2. `http://IP/start` — регистрация студента под псевдонимом.
3. `http://IP/teacher/login` — пароль из `.env`.
4. В `data/logs/ai_errors.log` не должно быть ошибок OpenRouter (если ключ пустой — ИИ молча отключён, работает локальный банк).

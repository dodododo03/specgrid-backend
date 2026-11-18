# SpecGrid 배포 가이드 (AWS EC2 + Docker Compose)

서버 한 대에 **웹 앱 + MariaDB + Redis**를 Docker로 띄우고, 서버에 직접 설치한 **nginx**가
HTTPS와 사진 파일을 담당하는 구성입니다.

```
인터넷 ──443/80──▶ nginx (EC2에 설치, Let's Encrypt 인증서)
                     ├─ /media/*  → /srv/specgrid/data/media (사진 파일을 디스크에서 바로 제공)
                     └─ 그 외     → 127.0.0.1:8000 ─▶ [app] FastAPI + 프론트엔드 (Docker)
                                                      ├─▶ [db]    MariaDB 12.3.3 (외부 공개 안 함)
                                                      └─▶ [redis] Redis (외부 공개 안 함)
[migrate] 시작할 때 한 번 DB 마이그레이션을 실행하고 종료 (DDL 권한 계정은 이 컨테이너만 가짐)
```

| 파일 | 역할 |
|---|---|
| `Dockerfile` | 앱 이미지 (Python 3.14, root가 아닌 사용자로 실행) |
| `docker-compose.yml` | app / migrate / db / redis 정의, 포트·데이터 위치·비밀번호 분리 |
| `deploy/env.production.example` | 서버용 `.env` 견본 |
| `deploy/mariadb/init/01-accounts.sh` | DB 첫 시작 때 DB와 계정 2개 생성 |
| `deploy/harden-db.sh` | 앱 계정 권한 최소화 + 점검 (`scripts/check_db_security.py`) |
| `deploy/nginx/specgrid.conf` | nginx 사이트 설정 (WebSocket, 사진, 보안 헤더, 업로드 크기) |
| `deploy/deploy.sh` | 업데이트 배포 (pull → 빌드 → 재시작 → 헬스 체크) |
| `deploy/backup.sh` | DB + 사진 매일 백업 (14일 보관) |
| `deploy/crontab.example` | 백업, 활동 기록 정리 예약 |

---

## 1. 서버 준비 (한 번만)

EC2: **Ubuntu 24.04**, t3.micro(또는 t2.micro), 디스크 20GB 이상.
보안 그룹 인바운드: `22`(내 IP만), `80`, `443`. **3306, 6379, 8000은 열지 않습니다.**

```bash
# 메모리 1GB라 빌드 중 멈추지 않도록 스왑 2GB
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Docker + compose 플러그인, nginx, certbot
sudo apt update && sudo apt install -y ca-certificates curl git nginx certbot python3-certbot-nginx
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # 적용하려면 로그아웃 후 다시 접속
sudo timedatectl set-timezone Asia/Seoul   # (선택) 로그·cron 시각을 한국 시간으로
```

## 2. 코드와 설정

```bash
sudo mkdir -p /srv/specgrid && sudo chown $USER: /srv/specgrid
git clone https://github.com/dodododo03/specgrid-backend.git /srv/specgrid
cd /srv/specgrid

cp deploy/env.production.example .env && chmod 600 .env
python3 -c "import secrets;print(secrets.token_urlsafe(32))"   # 비밀값마다 새로 생성해서 붙여넣기
nano .env        # 비밀번호 5개, MEDIA_BASE_URL의 도메인, KAKAO_JS_KEY

mkdir -p data/media logs
sudo chown 10001:10001 data/media   # 컨테이너 안 앱 사용자(uid 10001)가 사진을 쓸 수 있게
```

> `.env`는 **서버 밖 안전한 곳에도 보관**하세요. 특히 `LOG_HASH_KEY`는 한 번 정하면 바꾸지 않습니다.

## 3. 실행

```bash
docker compose up -d --build        # 첫 빌드는 몇 분 걸림
docker compose ps                    # app, db, redis가 running(healthy), migrate는 exited (0)
curl http://127.0.0.1:8000/api/v1/health    # {"status":"ok","database":"ok","redis":"ok"}
./deploy/harden-db.sh                # 마지막 줄이 "모든 점검 통과"여야 함
```

## 4. nginx + HTTPS

```bash
sudo cp deploy/nginx/specgrid.conf /etc/nginx/sites-available/specgrid
sudo sed -i 's/YOUR_DOMAIN/내도메인.com/g' /etc/nginx/sites-available/specgrid
sudo ln -s /etc/nginx/sites-available/specgrid /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d 내도메인.com        # 이메일 입력, 약관 동의 → HTTPS + 자동 갱신 설정
```

nginx(www-data)가 사진 폴더를 읽을 수 있어야 합니다: `/srv/specgrid`와 `data`가 755인지 확인.

## 5. 예약 작업

```bash
crontab deploy/crontab.example && crontab -l
./deploy/backup.sh                   # 한 번 직접 실행해서 backups/ 에 파일이 생기는지 확인
```

## 6. 업데이트 배포 (코드 바꾼 뒤)

```bash
cd /srv/specgrid && ./deploy/deploy.sh
```
새 마이그레이션이 **테이블을 추가**했다면 `scripts/harden_db_privileges.sql`에 그 테이블을 넣고
`./deploy/harden-db.sh`를 다시 실행합니다.

## 7. 복구

```bash
gunzip -c backups/db-YYYYmmdd-HHMM.sql.gz | docker compose exec -T db mariadb -uroot -p
tar -xzf backups/media-YYYYmmdd-HHMM.tar.gz -C data/
```
백업이 서버 디스크에만 있으면 서버를 잃을 때 같이 잃습니다. 가끔 `scp`로 내 PC에 복사해 두세요.

---

## 배포 전 체크리스트

**공개 전에 반드시**
- [ ] 도메인 준비 (구매 또는 무료 서브도메인) — HTTPS와 카카오맵에 필요
- [ ] `.env`의 비밀번호·키 5개가 새로 생성한 값인지 (로컬 값 재사용 금지), `chmod 600 .env`
- [ ] `./deploy/harden-db.sh` → "모든 점검 통과"
- [ ] HTTPS 접속 확인, `http://`가 `https://`로 넘어가는지
- [ ] 보안 그룹에 22(내 IP만)·80·443만 열려 있는지. `sudo ss -tlnp`에서 3306·6379가 안 보이고 8000은 `127.0.0.1`에만
- [ ] 카카오 디벨로퍼스 > JavaScript SDK 도메인에 `https://내도메인` 추가
- [ ] `frontend/js/views/legal.js`의 **〔미정〕** 채우기: 운영자, 개인정보 보호책임자, 연락처, 시행일, AWS 리전(서울 `ap-northeast-2` 권장)
- [ ] 백업 cron 등록 + `backup.sh` 수동 1회 성공, 활동 기록 정리 cron 등록
- [ ] AWS Budgets 비용 알림 설정

**배포 후 확인**
- [ ] 회원가입(중복 확인, 약관 동의) → 로그인 → 프로필 사진 → 상품 등록(사진) → 채팅(실시간) → 거래 → 회원 탈퇴
- [ ] 서버 재부팅(`sudo reboot`) 후 자동으로 다시 뜨는지 (`restart: unless-stopped`)
- [ ] `docker compose logs app --tail=50`에 에러가 없는지

## 문제 해결

| 증상 | 확인 |
|---|---|
| `migrate` exited (1) | `docker compose logs migrate` — `.env`의 DB 비밀번호가 DB 첫 생성 때와 다른 경우가 많음 (DB 계정은 **첫 시작 때만** 만들어짐) |
| 사진 업로드 500 | `ls -ld data/media` 소유자가 10001인지 |
| 사진이 안 보임 (404) | `MEDIA_BASE_URL`이 `https://도메인/media`인지, nginx `alias` 경로 |
| 채팅이 실시간으로 안 옴 | nginx 설정의 `/api/v1/chat/ws` 블록(Upgrade 헤더) 적용 여부 |
| 지도가 안 뜸 | 카카오 SDK 도메인 등록, `KAKAO_JS_KEY` |
| 빌드 중 서버 멈춤 | 스왑 설정 확인 (`free -h`) |

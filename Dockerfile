FROM python:3.12-slim

# 環境変数設定
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 作業ディレクトリの設定
WORKDIR /app

# 必要なパッケージのインストール
RUN apt-get update && apt-get install -y \
    curl \
    imagemagick \
    iputils-ping \
    libgl1-mesa-dev \
    libmagickwand-dev \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-jpn \
    tesseract-ocr-eng \
    tesseract-ocr-ell \
    && rm -rf /var/lib/apt/lists/*

# requirements.txtをコピーしてインストール
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# ポートの公開
EXPOSE 5000

# コンテナ起動時のコマンド
CMD ["python3", "app/main.py"]

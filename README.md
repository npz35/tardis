# TARDIS

PDF翻訳Webアプリ TARDIS（Translation And Reviewing Documents Interface Service）

## 概要

このアプリケーションは、ユーザーがアップロードしたPDFファイル（主に英語）を日本語に翻訳し、元のレイアウトを維持したまま新しいPDFファイルとして出力するWebアプリケーションです。翻訳にはllama.cppを利用したOpenAI互換APIを使用します。

## 機能

- PDFファイルのアップロード
- PDFからのテキスト、画像、図表の抽出と構造解析 (pdfminer.six)
- 翻訳単位の決定と結合
- 生成AI（llama.cpp）による日本語翻訳
- 元のレイアウトを維持したPDFの生成・出力 (pypdf, ReportLab)
- **PDFから図表のみを抽出したPDFの生成・出力** (pypdf, ReportLab)
    - **図表が検出されなかったページも白紙ページとして出力します。**
- ファイルサイズ制限、PDF形式エラー、ディスク容量不足、翻訳APIエラーなど、各種エラーハンドリング

## 技術スタック

- **バックエンド**: Python, Flask, Flask-SocketIO
- **PDF処理**: pdfminer.six, pypdf, ReportLab
- **翻訳API**: llama.cpp (OpenAI互換API)
- **フロントエンド**: HTML, CSS, JavaScript, Socket.IO
- **コンテナ化**: Docker, Docker Compose
- **テスト**: pytest

## ディレクトリ構成

```shell
tardis/
├── .gitignore                     # Git管理対象外ファイル
├── README.md                      # このドキュメント
├── AGENTS.md                      # コーディングアシスタント向けドキュメント
├── Dockerfile                     # Docker設定
├── app/
│   ├── __init__.py                # 空ファイル（パッケージ化）
│   ├── config.py                  # 設定ファイル
│   ├── figure_extractor.py        # 図表抽出モジュール
│   ├── gen_sample_pdf.py          # サンプルPDF生成スクリプト
│   ├── main.py                    # メインアプリケーション
│   ├── pdf_document_manager.py    # PDFドキュメント管理モジュール
│   ├── pdf_text_layout.py         # 翻訳済みテキストのレイアウト計算と描画モジュール
│   ├── pdf_text_manager.py        # PDFテキスト管理モジュール
│   ├── translator.py              # 翻訳API連携モジュール
│   └── utils.py                   # ユーティリティ関数
├── docker-compose.yml             # Docker Compose設定
├── logs/                          # アプリケーションログ
├── outputs/                       # 翻訳済みファイル
├── requirements.txt               # 依存関係
├── scripts/                       # スクリプトファイル
├── static/
│   └── css/
│       └── style.css              # スタイルシート
├── templates/
│   └── index.html                 # フロントエンド（HTML）
├── tests/                         # テストコード
└── uploads/                       # アップロードされたファイル
```

## セットアップと実行

### 前提条件

- Python 3.8+
- Docker
- Docker Compose
- llama.cpp (ローカル環境で実行)

### フォント設定

[IPA Font ダウンロード](https://moji.or.jp/ipafont/ipafontdownload/)からフォントファイル一式をダウンロードします。
ダウンロードしたTrueType Fontファイルを`static/fonts`ディレクトリに配置します。

```plaintxt
static/fonts/
├── ipaexg.ttf
└── ipaexm.ttf
```

### 開発環境の起動

1.  リポジトリをクローンします。
2.  Docker Composeを使用して開発環境を起動します。
    ```shell
    docker-compose up -d
    ```
3.  アプリケーションにアクセスします: `http://localhost:5000`

## エラーハンドリング

アプリケーションは、ファイルアップロード時（サイズ超過、拡張子不正）、PDF処理時（破損、解析エラー）、翻訳API通信時（タイムアウト、接続エラー、レート制限）など、様々なシナリオでエラーハンドリングを実装しています。エラーが発生した場合は、ユーザーに分かりやすいメッセージが表示されます。

## 実装の詳細

- **PDFドキュメント管理**: `app/pdf_document_manager.py`
    - PDFドキュメント全体の管理とワークフローの調整を行います。
- **PDFテキスト管理**: `app/pdf_text_manager.py`
    - `pdfminer.six` を使用してPDFからテキストを抽出し、`pypdf` を使用して元のテキスト領域を削除します。
- **PDFテキストレイアウト**: `app/pdf_text_layout.py`
    - `ReportLab` を使用して、翻訳済みテキストのレイアウトを計算し、描画します。
- **レイアウト計算**: `app/pdf_layout_calculator.py`
    - レイアウト調整に必要な情報を計算します。
- **図表抽出**: `app/figure_extractor.py`
    - `pdfminer.six` を使用してPDFから図表を抽出し、`PIL (Pillow)` を使用して画像をPNG形式に変換します。
    - `ReportLab` を使用して図表のみのPDFを生成し、図表が検出されなかったページも白紙ページとして出力します。

## テスト

単体テストは `tests/` ディレクトリに配置されており、`pytest` を使用して実行できます。
ファイルアップロード時のエラーハンドリング（ファイルサイズ超過、拡張子不正、ディスク容量不足、PDF解析エラー）を網羅するテストスイートが作成されています。

テストは Docker コンテナ上で行います。
テストを実行するには、以下のコマンドを使用してください。
```shell
docker-compose exec -T app pytest
```

### API疎通テスト

OpenAI互換API経由で、LLMへアクセスが可能なのかは以下のコマンドでテストできます。

```shell
./scripts/check_api.bash
```

## 注意事項

- 翻訳APIはllama.cppを使用（ローカル環境のみがターゲット）
- ファイルサイズの上限は16MB
- 日本語フォントはIPAex明朝を使用

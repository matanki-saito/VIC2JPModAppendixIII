#!/usr/bin/env python
# -*- coding:utf-8 -*-

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from os.path import join
from pathlib import Path

from boto3.session import Session

from special_escape import generate_encoder, generate_printer

_ = join

ignore_key_pattern = r"(^PROV[0-9]+$)|(^[A-Z]{3}$)|(^[A-Z]{3}_ADJ$)"
ignore_key_list = []


def build_yml_from_raw_json(in_dir_path,
                            out_dir_path,
                            ignore_keys_pattern,
                            ignore_keys_list):
    """
    raw jsonからymlを組み立てる
    :param in_dir_path: 入力パス
    :param out_dir_path: 出力パス
    :param ignore_keys_pattern: 除外キーパターン
    :param ignore_keys_list 強制除外キーリスト
    :return:
    """

    encoder = generate_encoder("eu4", "txt")
    printer = generate_printer("ck2", "txt")

    for f in Path(in_dir_path).glob("*.json"):
        result = ["#CODE;ENGLISH;FRENCH;GERMAN;;SPANISH;;;;;;;;;x"]

        # JSONを読み込んでymlに変換
        with open(str(f), "rt", encoding='utf-8') as fr:
            for item in json.loads(fr.read()):
                key = item['key']
                original = item['original']
                translation = item['translation']

                if key in ignore_keys_list or ignore_keys_pattern.match(key) or translation == "":
                    result.append('{};{};;;;;;;;;;;;;x'.format(key, original))
                else:
                    result.append('{};{};;;;;;;;;;;;;x'.format(key, translation))

        # ファイルに保存
        root, ext = os.path.splitext(f.name)
        encode = encoder(src_array=map(ord, "\r\n".join(result)))
        printer(src_array=encode, out_file_path=_(out_dir_path, root))


def download_trans_zip_from_paratranz(project_id,
                                      secret,
                                      out_file_path,
                                      base_url="https://paratranz.cn"):
    """
    paratranzからzipをダウンロードする
    :param project_id:
    :param secret:
    :param base_url:
    :param out_file_path:
    :return:
    """

    request_url = "{}/api/projects/{}/artifacts/download".format(base_url, project_id)
    req = urllib.request.Request(request_url)
    req.add_header("Authorization", secret)

    with open(out_file_path, "wb") as my_file:
        my_file.write(urllib.request.urlopen(req).read())

    return out_file_path


def assembly_app_mod_zip_file(resource_image_file_path,
                              resource_paratranz_trans_zip_file_path,
                              out_file_path):
    """
    Appモッドを作成
    :param resource_paratranz_trans_zip_file_path: Paratranzからダウンロードできるzipファイルのパス
    :param resource_image_file_path: 画像ファイルパス
    :param out_file_path: 出力ファイルパス
    :return:
    """
    with tempfile.TemporaryDirectory() as temp_dir_path:
        # raw/localisation
        temp_json_dir = _(temp_dir_path, "json")
        salvage_files_from_paratranz_trans_zip(out_dir_path=temp_json_dir,
                                               folder_list=["localisation"],
                                               paratranz_zip_path=resource_paratranz_trans_zip_file_path)

        # jsonを組み立てる
        out_dir_path = _(temp_dir_path, "out", "localisation")
        os.makedirs(out_dir_path, exist_ok=True)
        build_yml_from_raw_json(in_dir_path=temp_json_dir,
                                out_dir_path=out_dir_path,
                                ignore_keys_pattern=re.compile(ignore_key_pattern),
                                ignore_keys_list=ignore_key_list)

        # zip化する
        return shutil.make_archive(out_file_path, 'zip', root_dir=_(temp_dir_path, "out"))


def salvage_files_from_paratranz_trans_zip(out_dir_path,
                                           paratranz_zip_path,
                                           folder_list):
    with zipfile.ZipFile(paratranz_zip_path) as paratranz_zip:
        raw_files = filter(lambda name: name.startswith("raw/"), paratranz_zip.namelist())

        with tempfile.TemporaryDirectory() as temp_dir_path:
            paratranz_zip.extractall(path=temp_dir_path, members=raw_files)

            for folder in folder_list:
                shutil.copytree(_(temp_dir_path, "raw", folder), out_dir_path)


def generate_dot_mod_file(mod_title_name,
                          mod_file_name,
                          mod_tags,
                          mod_dependencies,
                          mod_image_file_path,
                          out_dir_path,
                          mod_user_dir_name=None):
    """
    .mod.modファイルを作る
    :param mod_title_name:
    :param mod_file_name: zipファイルの名前（.zipを含まない）
    :param mod_user_dir_name:ユーザ作業ディレクトリ名
    :param mod_tags: Set<String>型
    :param mod_dependencies: Set<String>型 依存先MOD
    :param mod_image_file_path:
    :param out_dir_path: 出力ディレクトリのパス
    :return: 出力ファイルパス
    """

    os.makedirs(out_dir_path, exist_ok=True)

    out_file_path = _(out_dir_path, "{}.mod".format(mod_file_name))

    if mod_user_dir_name is None:
        mod_user_dir_name = mod_file_name

    with open(out_file_path, "w", encoding="utf-8") as fw:
        lines = [
            'name="{}"'.format(mod_title_name),
            'archive="mod/{}.zip"'.format(mod_file_name),
            'user_dir="{}"'.format(mod_user_dir_name),
            'tags={}'.format("{" + " ".join(map(lambda c: '"{}"'.format(c), mod_tags)) + "}"),
            'picture="{}"'.format(mod_image_file_path),
            'dependencies={}'.format("{" + " ".join(map(lambda c: '"{}"'.format(c), mod_dependencies)) + "}"),
        ]

        fw.write("\n".join(lines))

    return out_file_path


def generate_distribution_file(url,
                               mod_file_path,
                               out_file_path):
    """
    trielaで使用する配布用設定ファイルを作成する。
    :param url:
    :param mod_file_path:
    :param out_file_path:
    :return:
    """

    with open(mod_file_path, 'rb') as fr:
        md5 = hashlib.md5(fr.read()).hexdigest()

    d_new = {'file_md5': md5,
             'url': url,
             'file_size': os.path.getsize(mod_file_path)}

    with open(out_file_path, "w", encoding="utf-8") as fw:
        json.dump(d_new, fw, indent=2, ensure_ascii=False)


def upload_mod_to_s3(upload_file_path,
                     name,
                     bucket_name,
                     access_key,
                     secret_access_key,
                     region):
    """
    S3にファイルをアップロードする
    :param upload_file_path:
    :param name:
    :param bucket_name:
    :param access_key:
    :param secret_access_key:
    :param region:
    :return: CDNのURL
    """
    session = Session(aws_access_key_id=access_key,
                      aws_secret_access_key=secret_access_key,
                      region_name=region)

    s3 = session.resource('s3')
    s3.Bucket(bucket_name).upload_file(upload_file_path, name)

    return "{}/{}".format("https://d3fxmsw7mhzbqi.cloudfront.net", name)


def pack_mod(out_file_path,
             mod_zip_path,
             mod_title_name,
             mod_file_name,
             mod_tags,
             mod_dependencies,
             mod_image_file_path,
             mod_user_dir_name=None):
    with tempfile.TemporaryDirectory() as temp_dir_path:
        # .mod.modファイルを作成する
        generate_dot_mod_file(
            mod_title_name=mod_title_name,
            mod_file_name=mod_file_name,
            mod_tags=mod_tags,
            mod_dependencies=mod_dependencies,
            mod_user_dir_name=mod_user_dir_name,
            mod_image_file_path=mod_image_file_path,
            out_dir_path=temp_dir_path)

        # zipをコピー
        shutil.copy(mod_zip_path, _(temp_dir_path, "{}.zip".format(mod_file_name)))

        return shutil.make_archive(out_file_path, 'zip', root_dir=temp_dir_path)


def main():
    # 一時フォルダ用意
    os.makedirs(_(".", "tmp"), exist_ok=True)
    os.makedirs(_(".", "out"), exist_ok=True)

    # 翻訳の最新版をダウンロードする
    p_file_path = _(".", "tmp", "paratranz.zip")
    if not os.path.exists(p_file_path):
        p_file_path = download_trans_zip_from_paratranz(
            project_id=2543,
            secret=os.environ.get("PARATRANZ_SECRET"),
            out_file_path=p_file_path)

    print("p_file_path:{}".format(p_file_path))

    # AppModを構築する
    app_mod_zip_file_path = assembly_app_mod_zip_file(
        resource_paratranz_trans_zip_file_path=p_file_path,
        resource_image_file_path=_(".", "resource", "title.jpg"),
        out_file_path=_(".", "tmp", "mod"))

    print("app_mod_zip_file_path:{}".format(app_mod_zip_file_path))

    # packする
    mod_pack_file_path = pack_mod(
        out_file_path=_(".", "out", "vic2_ap3_mod"),
        mod_file_name="jpmod_ap3_mod",
        mod_zip_path=app_mod_zip_file_path,
        mod_title_name="JPMOD Sub 2: English Map Names",
        mod_tags={"Translation", "Localisation"},
        mod_dependencies=["JPMOD Main 2: Text"],
        mod_image_file_path="title.jpg",
        mod_user_dir_name="JLM")

    print("mod_pack_file_path:{}".format(mod_pack_file_path))

    # S3にアップロード from datetime import datetime as dt
    from datetime import datetime as dt
    cdn_url = upload_mod_to_s3(
        upload_file_path=mod_pack_file_path,
        name=dt.now().strftime('%Y-%m-%d_%H-%M-%S-{}'.format("vic2-ap3")),
        bucket_name="triela-file",
        access_key=os.environ.get("AWS_S3_ACCESS_KEY"),
        secret_access_key=os.environ.get("AWS_S3_SECRET_ACCESS_KEY"),
        region="ap-northeast-1")

    print("cdn_url:{}".format(cdn_url))

    # URLはリンク先に置く
    print("::set-output name=download_url::{}".format(cdn_url))

    # distributionファイルを生成する
    generate_distribution_file(url=cdn_url,
                               out_file_path=_(".", "out", "dist.v2.json"),
                               mod_file_path=mod_pack_file_path)


if __name__ == "__main__":
    main()

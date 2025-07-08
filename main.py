#!/usr/bin/env python3

from gofilepy import gofile as gf
from os import path, environ, mkdir, getcwd, chdir, getenv, listdir, system, remove
from sys import exit, stdout, stderr
from typing import Dict, List
from requests import get, post
from concurrent.futures import ThreadPoolExecutor
from platform import system as ps
from hashlib import sha256
from shutil import move
from time import perf_counter
from pyperclip import copy
from colorama import init, Fore, Style

# Initialize colorama
init()


NEW_LINE: str = "\n" if ps() != "Windows" else "\r\n"

print(
    r"""
╭───────────────────────────────────────╮
│          Go File Sharing Tool         │
│                   v1.0                │
╰───────────────────────────────────────╯
"""
)


def UPLOAD(upload_dir=path.join(getcwd(), "Uploads")):
    if not path.exists(upload_dir):
        mkdir(upload_dir)
        print(f"{Fore.GREEN}Created 'Uploads' directory{Style.RESET_ALL}")
    up_files = listdir(upload_dir)
    if not up_files:
        print(f"{Fore.YELLOW}No files found in 'Uploads' folder!{Style.RESET_ALL}{NEW_LINE}")
    else:

        all_files_list = []  # Used as argument
        file_names = []  # Shown on screen

        for file in up_files:
            file_path = path.join(upload_dir, file)
            normalized_path = path.normpath(file_path)
            all_files_list.append(normalized_path)
            file_names.append(f"  {path.basename(normalized_path)}")
        print(f"Uploading the following {len(up_files)} file(s):")
        print(f"{Fore.CYAN}{NEW_LINE.join(file_names)}{Style.RESET_ALL}{NEW_LINE}")

        get_url = gf.gofile_upload(all_files_list, to_single_folder=False, export=False)
        copy(
            get_url
        )  # Manually add 'return url' to the end of gofile_upload() function of gofile.py (line: 144)
        print(NEW_LINE)


def DOWNLOAD(download_dir=path.join(getcwd(), "Downloads")):
    def die(_str: str) -> None:
        """
        Display a message of error and exit.

        :param _str: a string to be printed.
        :return:
        """

        stderr.write(_str + NEW_LINE)
        stderr.flush()
        print(NEW_LINE)
        system("pause" if ps() == "Windows" else "")
        exit(-1)

    def _print(_str: str) -> None:
        """
        Print a message.

        :param _str: a string to be printed.
        :return:
        """

        stdout.write(_str)
        stdout.flush()

    # increase max_workers for parallel downloads
    # defaults to 5 download at time
    class Main:
        def __init__(
            self, url: str, password: str | None = None, max_workers: int = 5
        ) -> None:
            try:
                if not url.split("/")[-2] == "d":
                    die(
                        f"{Fore.RED}The URL probably doesn't have an ID in it: {url}{Style.RESET_ALL}"
                    )

                self._id: str = url.split("/")[-1]
            except IndexError:
                die(f"{Fore.RED}Something is wrong with the URL: {url}{Style.RESET_ALL}")

            self._downloaddir: str | None = getenv("GF_DOWNLOADDIR")

            if self._downloaddir and path.exists(self._downloaddir):  # ./Downloads
                chdir(self._downloaddir)

            self._root_dir: str = path.join(getcwd(), self._id)  # ./Downloads/ID
            self._token: str = self._getToken()
            self._password: str | None = (
                sha256(password.encode()).hexdigest() if password else None
            )
            self._max_workers: int = max_workers

            # list of dictionaries format files and its respective path, filename and link
            self._files_link_list: List[Dict] = []

            self._createDir(self._id)
            self._parseLinks(self._id, self._token, self._password)
            self._threadedDownloads()

        def _threadedDownloads(self) -> None:
            """
            Parallelize the downloads.

            :return:
            """

            chdir(path.join(download_dir, ".."))  # 先切到最外層

            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                for item in self._files_link_list:
                    executor.submit(self._downloadContent, item, self._token, 16384)

        def _createDir(self, dirname: str) -> None:
            """
            creates a directory where the files will be saved if doesn't exist and change to it.

            :param dirname: name of the directory to be created.
            :return:
            """
            current_dir: str = getcwd()
            filepath: str = path.join(current_dir, dirname)

            try:
                mkdir(path.join(filepath))
            # if the directory already exist is safe to do nothing
            except FileExistsError:
                pass

        @staticmethod
        def _getToken() -> str:
            """
            Gets the access token of account created.

            :return: The access token of an account. Or exit if account creation fail.
            """

            headers: Dict = {
                "User-Agent": (
                    getenv("GF_USERAGENT") if getenv("GF_USERAGENT") else "Mozilla/5.0"
                ),
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
            }

            create_account_response: Dict = post(
                "https://api.gofile.io/accounts", headers=headers
            ).json()

            if create_account_response["status"] != "ok":
                die("Account creation failed!")

            return create_account_response["data"]["token"]

        @staticmethod
        def _downloadContent(
            file_info: Dict, token: str, chunk_size: int = 4096
        ) -> None:
            """
            Download a file.

            :param file_info: a dictionary with information about a file to be downloaded.
            :param token: the access token of the account.
            :param chunk_size: the number of bytes it should read into memory.
            :return:
            """

            if path.exists(file_info["path"]):
                if path.getsize(file_info["path"]) > 0:
                    _print(
                        f"{Fore.YELLOW}{file_info['filename']} already exist, skipping.{Style.RESET_ALL}"
                        + NEW_LINE
                    )

                    return

            filename: str = file_info["path"] + ".part"
            url: str = file_info["link"]

            headers: Dict = {
                "Cookie": "accountToken=" + token,
                "Accept-Encoding": "gzip, deflate, br",
                "User-Agent": (
                    getenv("GF_USERAGENT") if getenv("GF_USERAGENT") else "Mozilla/5.0"
                ),
                "Accept": "*/*",
                "Referer": url + ("/" if not url.endswith("/") else ""),
                "Origin": url,
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
            }

            # check for partial download and resume from last byte
            part_size: int = 0
            if path.isfile(filename):
                part_size = int(path.getsize(filename))
                headers["Range"] = f"bytes={part_size}-"

            has_size: str | None = None
            message: str = " "

            try:
                with get(
                    url, headers=headers, stream=True, timeout=(9, 27)
                ) as response_handler:
                    if (
                        (response_handler.status_code in (403, 404, 405, 500))
                        or (part_size == 0 and response_handler.status_code != 200)
                        or (part_size > 0 and response_handler.status_code != 206)
                    ):
                        _print(
                            f"Couldn't download the file from {url}."
                            + NEW_LINE
                            + f"Status code: {response_handler.status_code}"
                            + NEW_LINE
                        )

                        return

                    content_range = response_handler.headers.get("Content-Range")
                    has_size = (
                        response_handler.headers.get("Content-Length")
                        if part_size == 0
                        else content_range.split("/")[-1] if content_range is not None else None
                    )

                    if not has_size:
                        _print(
                            f"Couldn't find the file size from {url}."
                            + NEW_LINE
                            + f"Status code: {response_handler.status_code}"
                            + NEW_LINE
                        )

                        return

                    with open(filename, "ab") as handler:
                        total_size: float = float(has_size)

                        start_time: float = perf_counter()
                        for i, chunk in enumerate(
                            response_handler.iter_content(chunk_size=chunk_size)
                        ):
                            progress: float = (
                                (part_size + (i * len(chunk))) / total_size * 100
                            )

                            handler.write(chunk)

                            rate: float = (i * len(chunk)) / (
                                perf_counter() - start_time
                            )
                            unit: str = "B/s"
                            if rate < (1024):
                                unit = "B/s"
                            elif rate < (1024 * 1024):
                                rate /= 1024
                                unit = "KB/s"
                            elif rate < (1024 * 1024 * 1024):
                                rate /= 1024 * 1024
                                unit = "MB/s"
                            elif rate < (1024 * 1024 * 1024 * 1024):
                                rate /= 1024 * 1024 * 1024
                                unit = "GB/s"

                            _print("\r" + " " * len(message))

                            message = (
                                f"\r{file_info['filename']} - {part_size + i * len(chunk)}"
                                f" of {has_size} bytes  {round(progress, 1)}%  {round(rate, 1)}{unit}"
                            )

                            _print(message)
            finally:
                if has_size is not None and path.getsize(filename) == int(has_size):
                    _print("\r" + " " * len(message))

                    message = (
                        f"{Fore.GREEN}{file_info['filename']}{Style.RESET_ALL} - {path.getsize(filename)} of {has_size} bytes downloaded"
                        + NEW_LINE
                    )

                    _print(message)
                    move(filename, file_info["path"])

        def _cacheLink(self, filepath: str, filename: str, link: str) -> None:
            """
            Caches the link into the _files_link_list.

            :param filepath: file's path.
            :param filename: filename.
            :param link: link to be cached.
            :return:
            """

            self._files_link_list.append(
                {
                    "path": path.join(filepath, filename),
                    "filename": filename,
                    "link": link,
                }
            )

        def _parseLinks(
            self, _id: str, token: str, password: str | None = None
        ) -> None:
            """
            Parses for possible links recursively and populate a list with file's info.

            :param _id: url to the content.
            :param token: access token.
            :param password: content's password.
            :return:
            """

            url: str = (
                f"https://api.gofile.io/contents/{_id}?wt=4fd6sg89d7s6&cache=true"
            )

            if password:
                url = url + f"&password={password}"

            headers: Dict = {
                "User-Agent": (
                    getenv("GF_USERAGENT") if getenv("GF_USERAGENT") else "Mozilla/5.0"
                ),
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "Authorization": "Bearer" + " " + token,
            }

            response: Dict = get(url, headers=headers).json()

            if response["status"] != "ok":
                die(f"Failed to get a link as response from the {url}")

            data: Dict = response["data"]

            if data["type"] == "folder":
                children_ids: List[str] = data["children"]

                self._createDir(data["name"])
                chdir(data["name"])

                for child_id in children_ids:
                    child: Dict = data["children"][child_id]

                    if data["children"][child_id]["type"] == "folder":
                        self._parseLinks(child["code"], token, password)
                    else:
                        self._cacheLink(getcwd(), child["name"], child["link"])

                chdir(path.pardir)
            else:
                self._cacheLink(getcwd(), data["name"], data["link"])

    if __name__ == "__main__":
        try:
            url: str | None = None
            password: str | None = None
            url = input("Enter URL: ")

            # Run
            # download_dir = path.join(getcwd(), "Downloads")
            if not path.exists(download_dir):
                mkdir(download_dir)
                print(f"{Fore.GREEN}Created 'Downloads' directory{Style.RESET_ALL}")
                chdir(path.join(download_dir, ".."))

            environ["GF_DOWNLOADDIR"] = download_dir
            _print("Downloading files, please wait..." + NEW_LINE + NEW_LINE)
            Main(url=url, password=password, max_workers=5)
            print(NEW_LINE)
        except KeyboardInterrupt:
            exit(1)


while True:
    Option = input("Enter your choice: (1) Upload   (2) Download   (Q) Quit  " )
    if Option == "1":
        UPLOAD()
        continue
    elif Option == "2":
        DOWNLOAD()
        continue
    elif Option.lower() == "q":
        break


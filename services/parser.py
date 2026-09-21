import json
import logging
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import openai
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("parser")
if os.getenv("DEBUG", "false").lower() == "true":
    logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)
else:
    logger.addHandler(logging.NullHandler())


@dataclass
class Tender:
    number: str
    title: str
    customer: str
    price: str
    deadline: str
    description: str
    url: str
    positions: list[str] = None  # Список позиций товаров (SKU)

    def __post_init__(self):
        if self.positions is None:
            self.positions = []


@dataclass
class TenderFile:
    id: str
    title: str
    url: str
    extension: str
    local_path: str = ""


class RostenderParser:
    BASE_URL = "https://rostender.info"

    DEFAULT_REGIONS = {"tatarstan": "20", "kazan": "20", "moscow": "182394", "spb": "155429", "cfo": "1", "pfo": "7"}

    def __init__(self, email: str = None, password: str = None, downloads_dir: str = "downloads"):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        self.downloads_dir = Path(downloads_dir)
        self.cache_dir = Path("cache")
        for d in [self.downloads_dir, self.cache_dir]:
            d.mkdir(exist_ok=True)

        self.ai_client = None
        if key := os.getenv("OPENAI_API_KEY"):
            self.ai_client = openai.OpenAI(api_key=key, base_url="https://api.proxyapi.ru/openai/v1")

        self.regions_map = self._load_map("regions")
        self.branches_map = self._load_map("branches")

        self._fetch_remote_data()

        print(f"Загружено {len(self.regions_map)} регионов")
        print(f"Загружено {len(self.branches_map)} отраслей")

        self.is_logged_in = False
        if email and password:
            self._login(email, password)

    def _fetch_remote_data(self):
        try:
            r = self.session.get(f"{self.BASE_URL}/yiiajax/get-regions", headers={"X-Requested-With": "XMLHttpRequest"})
            if r.status_code == 200:
                data = r.json().get("result", [])

                with open("regions_data.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                for item in data:
                    self.regions_map[item["name"].lower()] = str(item["id"])
                    for d in item.get("districts", []):
                        self.regions_map[d["name"].lower()] = str(d["id"])

                self.regions_map.update(
                    {"москва": "182394", "спб": "155429", "питер": "155429", "татарстан": "20", "казань": "20"}
                )
                self._save_map("regions", self.regions_map)
        except Exception as e:
            logger.debug(f"Regions fetch error: {e}")

        try:
            r = self.session.get(
                f"{self.BASE_URL}/yiiajax/get-branches", headers={"X-Requested-With": "XMLHttpRequest"}
            )
            if r.status_code == 200:
                data = r.json().get("result", [])

                with open("branches_data.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                self.branches_map = {}
                for item in data:
                    for child in item.get("children", []):
                        self.branches_map[child["name"].lower()] = str(child["id"])

                self._save_map("branches", self.branches_map)
        except Exception as e:
            logger.debug(f"Branches fetch error: {e}")

    def _login(self, email, password):
        print("Попытка авторизации...")
        try:
            login_url = f"{self.BASE_URL}/login"
            resp = self.session.get(login_url)
            soup = BeautifulSoup(resp.text, "html.parser")
            csrf = soup.find("input", {"name": re.compile(r"csrf", re.I)})

            data = {"LoginForm[username]": email, "LoginForm[password]": password, "LoginForm[rememberMe]": "1"}
            if csrf:
                data["_csrf"] = csrf["value"]

            post = self.session.post(login_url, data=data)
            if post.status_code == 200 and "logout" in post.text.lower():
                self.is_logged_in = True
                print("[OK] Авторизация успешна")
            else:
                print("[X] Авторизация не удалась")
        except Exception as e:
            logger.debug(f"Login error: {e}")
            print("[X] Ошибка авторизации")

    def _load_map(self, name: str) -> dict:
        path = self.cache_dir / f"{name}_map.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        return {}

    def _save_map(self, name: str, data: dict):
        try:
            with open(self.cache_dir / f"{name}_map.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load_json_data(self, filename: str) -> dict:
        if Path(filename).exists():
            with open(filename, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _resolve_entity(self, query: str, entity_type: str, keyword: str = "") -> str | None:
        if not query:
            return None
        key = query.lower().strip()

        cache_map = self.regions_map if entity_type == "regions" else self.branches_map

        if key in cache_map:
            return cache_map[key]

        if entity_type == "regions" and key in self.DEFAULT_REGIONS:
            return self.DEFAULT_REGIONS[key]

        if not self.ai_client:
            return None

        context = "Список регионов РФ." if entity_type == "regions" else "Список отраслей."
        additional_context = ""
        if entity_type == "branches" and keyword:
            additional_context = (
                f" Контекст (ключевое слово): '{keyword}'. Используй его для выбора наиболее подходящей тематики."
            )

        options_list = []
        for name, eid in list(cache_map.items())[:800]:
            options_list.append(f"{eid}: {name}")

        options_text = "\n".join(options_list)

        prompt = (
            f"Твоя задача: выбрать из списка ID категории, которая лучше всего подходит под запрос.\n"
            f"Запрос пользователя: '{query}'\n"
            f"{additional_context}\n"
            f"Тип данных: {context}\n\n"
            f"Список доступных вариантов (ID: Название):\n"
            f"{options_text}\n\n"
            f"Правила:\n"
            f"1. Верни СТРОГО и ТОЛЬКО JSON с ID выбранной категории.\n"
            f"2. Формат: {{'id': '123'}}\n"
            f"3. Если ничего не подходит, верни null."
        )

        try:
            resp = self.ai_client.chat.completions.create(
                model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0
            )
            content = resp.choices[0].message.content.replace("```json", "").replace("```", "").strip()
            if content == "null":
                return None

            res = json.loads(content)
            found_id = str(res.get("id", ""))

            if found_id:
                if found_id in cache_map.values():
                    cache_map[key] = found_id
                    self._save_map(entity_type, cache_map)
                    print(f"  [AI] '{query}' -> ID: {found_id}")
                    return found_id
                else:
                    logger.debug(f"AI returned invalid ID: {found_id}")

        except Exception as e:
            logger.debug(f"AI resolution error: {e}")
            pass
        return None

    def search(
        self,
        region: str,
        industry: str,
        keyword: str = None,
        keywords: str = None,
        exceptions: str = None,
        limit: int = 40,
    ) -> list[Tender]:
        """
        Поиск тендеров.

        Args:
            region: Регион
            industry: Отрасль
            keyword: Простое ключевое слово (для обычного поиска)
            keywords: Продвинутый синтаксис keywords из пресета (*, ~N, "")
            exceptions: Продвинутый синтаксис исключений (*, ~N, "")
            limit: Лимит результатов
        """
        # Используем keywords если есть, иначе keyword
        search_keywords = keywords or keyword or ""

        # Преобразуем переносы строк в запятые для формата rostender.info
        if keywords:
            search_keywords = search_keywords.replace("\n", ",")

        params = {"keywords": search_keywords}

        rid = self._resolve_entity(region, "regions")
        if rid:
            params["geo[]"] = rid

        # Для的行业 используем keyword для резолвинга ID
        bid = self._resolve_entity(industry, "branches", keyword or search_keywords)
        if bid:
            params["branch[]"] = bid

        # Добавляем исключающие слова (преобразуем переносы в запятые)
        if exceptions:
            params["exceptions"] = exceptions.replace("\n", ",")

        # Фильтр по дате - только актуальные тендеры (сегодня)
        # from datetime import datetime
        # today = datetime.now().strftime("%d.%m.%Y")
        # params['dte_from'] = today

        r_name = next((k.title() for k, v in self.regions_map.items() if v == rid), rid) if rid else "Все"
        b_name = next((k.title() for k, v in self.branches_map.items() if v == bid), bid) if bid else "Все"

        kw_info = " (продвинутый)" if keywords else ""
        exc_info = ", Исключения='Да'" if exceptions else ""
        # print(f"\nПараметры: Регион='{r_name}', Отрасль='{b_name}', Keywords='{search_keywords[:50]}...'{kw_info}{exc_info}, С даты={today}")
        print(
            f"\nПараметры: Регион='{r_name}', Отрасль='{b_name}', Keywords='{search_keywords[:50]}...'{kw_info}{exc_info}"
        )

        tenders = []
        try:
            resp = self.session.get(f"{self.BASE_URL}/extsearch", params=params, timeout=30)
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = soup.select("article.tender-row") or soup.select(".search-item")
            logger.debug(f"Found {len(cards)} cards")

            for card in cards[:limit]:
                if t := self._parse_card(card):
                    tenders.append(t)
        except Exception as e:
            logger.debug(f"Search error: {e}")
            pass
        return tenders

    def _parse_card(self, card) -> Tender | None:
        try:
            link = card.select_one("a.tender-info__description") or card.select_one('a[href*="/tender"]')
            if not link:
                return None

            href = link["href"]
            url = self.BASE_URL + href if href.startswith("/") else href

            num = "N/A"
            if num_node := card.select_one(".tender__number"):
                if m := re.search(r"(\d{8})", num_node.text):
                    num = m.group(1)

            price = "—"
            if p_node := card.select_one(".starting-price__price") or card.select_one(".price"):
                price = p_node.get_text(strip=True)

            return Tender(
                number=num,
                title=link.get_text(strip=True),
                customer=card.select_one(".tender-customer__name").get_text(strip=True)
                if card.select_one(".tender-customer__name")
                else "Не указан",
                price=price,
                deadline=card.select_one(".tender__countdown-text").get_text(strip=True)
                if card.select_one(".tender__countdown-text")
                else "",
                description=link.get_text(strip=True),
                url=url,
            )
        except Exception as e:
            logger.debug(f"Card parse error: {e}")
            return None

    def _extract_positions(self, soup: BeautifulSoup) -> list[str]:
        """Извлечь позиции товаров из таблицы table-positions-container."""
        positions = []

        # Ищем контейнер с позициями
        container = soup.find("div", class_="table-positions-container")
        if container:
            # Ищем все строки с позициями
            rows = container.find_all("div", class_="table-positions-raw")

            for row in rows:
                # Пропускаем заголовок таблицы
                if "table-header" in row.get("class", []):
                    continue

                # Ищем ячейку с названием (cell-name)
                name_cell = row.find("div", class_="cell-name")
                if name_cell:
                    # Извлекаем текст из span или напрямую из ячейки
                    span = name_cell.find("span")
                    name = span.get_text(strip=True) if span else name_cell.get_text(strip=True)

                    # Добавляем если не пустой и не повторяется
                    if name and name not in positions:
                        positions.append(name)

        logger.debug(f"Extracted {len(positions)} positions")
        return positions

    def get_details(self, url: str) -> dict:
        details = {"documents": [], "requirements": "", "description": "", "positions": []}
        try:
            resp = self.session.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            html = resp.text

            # Извлекаем позиции товаров
            details["positions"] = self._extract_positions(soup)

            if desc_div := soup.find("div", class_="description"):
                details["description"] = desc_div.get_text(separator=" ", strip=True)[:3000]

            if req_span := soup.find("span", string=re.compile(r"Требования", re.I)):
                if parent := req_span.find_parent("div"):
                    details["requirements"] = parent.get_text(separator="\n", strip=True)[:5000]

            if m := re.search(r"var\s+tendersData\s*=\s*(\{[^;]+\})", html):
                try:
                    data = json.loads(m.group(1))
                    for k in data:
                        for f in data[k].get("files_by_date", {}).values():
                            for x in f:
                                if x.get("link"):
                                    details["documents"].append(
                                        TenderFile(
                                            id=str(x.get("id", "")),
                                            title=x.get("title", "file"),
                                            url=x["link"],
                                            extension=x.get("extension", ""),
                                        )
                                    )
                except (KeyError, TypeError, ValueError):
                    pass

            if not details["documents"]:
                for item in soup.select(".tender-files__item"):
                    if a := item.select_one("a[href]"):
                        details["documents"].append(
                            TenderFile(id="", title=item.get_text(strip=True), url=a["href"], extension="")
                        )

        except Exception as e:
            logger.debug(f"Details error: {e}")
            pass
        return details

    def download_files(self, files: list[TenderFile], folder: str) -> str:
        target = self.downloads_dir / folder
        target.mkdir(exist_ok=True)
        count = 0

        for f in files:
            if not f.url:
                continue

            safe_title = re.sub(r"[^\w\-\.\s]", "_", f.title).strip()
            print(f"Скачивание: {safe_title}")

            name = f"{f.id}_{safe_title}"
            path = target / name

            try:
                headers = {"Referer": self.BASE_URL} if "rostender" in f.url else {}
                with self.session.get(f.url, headers=headers, stream=True, timeout=60) as r:
                    content_type = r.headers.get("Content-Type", "").lower()
                    if "html" in content_type:
                        if not path.suffix:
                            path = path.with_suffix(".html")

                    r.raise_for_status()

                    with open(path, "wb") as out:
                        for chunk in r.iter_content(8192):
                            out.write(chunk)

                f.local_path = str(path)

                if path.suffix == ".zip":
                    try:
                        with zipfile.ZipFile(path, "r") as z:
                            extract_path = target / f"{f.id}_extracted"
                            z.extractall(extract_path)
                            print(f"  -> Распакован в {extract_path.name}")
                    except Exception:
                        print("  -> Ошибка распаковки ZIP")

                count += 1
            except Exception as e:
                logger.debug(f"Download error {f.title}: {e}")
                print(f"  -> Ошибка: {e}")
                pass

        print(f"Скачано файлов: {count}/{len(files)}")
        return str(target) if count > 0 else ""

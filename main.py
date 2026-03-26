import asyncio
import random
import aiosqlite
import os
from datetime import datetime
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

# 【关键】兼容性导入 MessageChain，适配不同版本的 AstrBot
try:
    from astrbot.api.message_components import MessageChain
except ImportError:
    try:
        from astrbot.api.model import MessageChain
    except ImportError:
        from astrbot.api.event.entities import MessageChain

@register("daily_length_db", "GeMio", "SQL版长度插件(修复艾特兼容性)", "1.2.3")
class DailyLengthPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.db_path = os.path.join(os.path.dirname(__file__), "data.db")

    async def _init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS records (
                    user_id TEXT PRIMARY KEY,
                    nickname TEXT,
                    length REAL,
                    record_date TEXT
                )
            ''')
            await db.commit()

    async def _get_user_nickname(self, event: AstrMessageEvent, user_id: str) -> str:
        name = event.get_sender_name()
        return name if name else f"用户_{user_id[-4:]}"

    @filter.command("今日长度")
    async def handle_length(self, event: AstrMessageEvent):
        await self._init_db()
        user_id = str(event.get_sender_id())
        today = datetime.now().strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT length, nickname FROM records WHERE user_id = ? AND record_date = ?", 
                (user_id, today)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                length, nickname = row
                is_new = False
            else:
                length = round(random.uniform(1, 30), 2)
                nickname = await self._get_user_nickname(event, user_id)
                is_new = True
                await db.execute(
                    "REPLACE INTO records (user_id, nickname, length, record_date) VALUES (?, ?, ?, ?)",
                    (user_id, nickname, length, today)
                )
                await db.commit()

        # 【核心修复】使用 MessageChain 构造带艾特的消息
        chain = MessageChain()
        # 尝试使用通用的 at 方法，这在大多数适配器中都是标准的
        chain.at(user_id) 
        
        prefix = "（今日已锁定）" if not is_new else ""
        chain.text(f" {nickname} 今天的长度是 {length}cm！{prefix}")
        
        yield event.chain_result(chain)

    @filter.command("长度排行")
    async def handle_rank(self, event: AstrMessageEvent):
        await self._init_db()
        today = datetime.now().strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT nickname, length FROM records WHERE record_date = ? ORDER BY length DESC", 
                (today,)
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            yield event.plain_result("今天还没有人参与测试哦~")
            return

        chunk_size = 15
        header = "🏆 今日长度排行榜 🏆\n" + "—" * 20 + "\n"
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            rank_text = header if i == 0 else ""
            for index, (nick, l_val) in enumerate(chunk, start=i + 1):
                rank_text += f"{index}. {nick}: {l_val:.2f}cm\n"
            yield event.plain_result(rank_text.strip())
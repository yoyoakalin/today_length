import asyncio
import random
import aiosqlite
import os
from datetime import datetime
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

@register("daily_length_db", "GeMio", "SQL异步长度插件(修复艾特版)", "1.2.2")
class DailyLengthPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 保持在 Windows 环境下的路径兼容性
        self.db_path = os.path.join(os.path.dirname(__file__), "data.db")

    async def _init_db(self):
        """初始化数据库表"""
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
        """安全获取昵称，处理非数字 ID"""
        name = event.get_sender_name()
        return name if name else f"用户_{user_id[-4:]}"

    @filter.command("今日长度")
    async def handle_length(self, event: AstrMessageEvent):
        await self._init_db()
        # 统一使用字符串 ID
        user_id = str(event.get_sender_id())
        today = datetime.now().strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path) as db:
            # 1. 查询今日记录
            async with db.execute(
                "SELECT length, nickname FROM records WHERE user_id = ? AND record_date = ?", 
                (user_id, today)
            ) as cursor:
                row = await cursor.fetchone()

            if row:
                length, nickname = row
                is_new = False
            else:
                # 2. 生成新记录（保留两位小数）
                length = round(random.uniform(1, 30), 2)
                nickname = await self._get_user_nickname(event, user_id)
                is_new = True

                await db.execute(
                    "REPLACE INTO records (user_id, nickname, length, record_date) VALUES (?, ?, ?, ?)",
                    (user_id, nickname, length, today)
                )
                await db.commit()

        # 3. 构造消息内容
        # 使用 event.at_sender() 替代手动导入 MessageChain，避免路径报错
        prefix = "（今日已锁定）" if not is_new else ""
        result_text = f" {nickname} 今天的长度是 {length}cm！"
        
        # 核心修复：通过简易方式发送带艾特的消息
        yield event.plain_result(event.at_sender() + prefix + result_text)

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

        # 分页逻辑
        chunk_size = 15
        header = "🏆 今日长度排行榜 🏆\n" + "—" * 20 + "\n"
        
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            rank_text = header if i == 0 else ""
            for index, (nick, l_val) in enumerate(chunk, start=i + 1):
                rank_text += f"{index}. {nick}: {l_val:.2f}cm\n"
            
            yield event.plain_result(rank_text.strip())
# -*- coding: utf-8 -*-
# jsl_data_updater.py - Version 0502 集思录(JSL)看板专属-数据大一统更新器 (极速多线程版)
import os
import sys
import logging
import concurrent.futures
import time
from datetime import datetime, timedelta
import pandas as pd
import sqlite3
import requests
import re

# 强制禁用系统代理，避免 VPN(如 127.0.0.1:10808) 影响新浪/东财访问
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

# 核心：复用主项目的 arbcore 底层能力
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from arbcore.fetchers.data_fetcher import data_fetcher

# 配置日志：同时输出到控制台和文件
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"jsl_data_updater_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)
logger = logging.getLogger(__name__)
logging.getLogger('arbcore.fetchers.data_fetcher').setLevel(logging.WARNING)

class JslDataUpdater:
    def __init__(self):
        # 我们统一只用这一个数据库，抛弃其他的
        self.db_path = os.path.join(os.path.dirname(__file__), "jsl_monitor.db")
        self._ensure_db_exists()
        self.config = self._load_config()
        # 初始化时，将CSV中的基础信息同步到数据库字典表中
        self._sync_fund_info()
    
    def _ensure_db_exists(self):
        """确保数据库和表存在 (主从表最佳实践结构 - 增强版)"""
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        cursor = conn.cursor()
        
        # 1. 基金基础信息表 (字典表：扩充了所有静态和半静态配置)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fund_info (
                fund_code TEXT PRIMARY KEY,
                fund_name TEXT NOT NULL,
                category TEXT NOT NULL,
                idx_code TEXT,
                idx_name TEXT,
                pos_ratio REAL,
                purchase_fee TEXT,
                purchase_status TEXT,
                redemption_fee TEXT,
                redemption_status TEXT,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 2. 基金历史数据表 (流水表：按日存储现价、净值、折溢价率 - 保持不变)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fund_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                fund_code TEXT NOT NULL,
                price REAL,
                nav REAL,
                premium REAL,
                volume REAL,
                shares REAL,
                turnover_rate REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, fund_code)
            )
        ''')
        
        # 3. 访问防刷同步状态表 (保持不变)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS access_sync_status (
                sync_date TEXT NOT NULL,
                access_source TEXT NOT NULL,
                sync_time TEXT,
                PRIMARY KEY (sync_date, access_source)
            )
        ''')
        
        # 4. 指数历史数据表 (新增)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS index_history (
                symbol TEXT NOT NULL,
                date TEXT NOT NULL,
                close REAL,
                source TEXT,
                PRIMARY KEY (symbol, date)
            )
        ''')
        
        # 创建索引提升查询速度
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON fund_info(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_code_date ON fund_history(fund_code, date DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol_date ON index_history(symbol, date DESC)')
        
        conn.commit()
        conn.close()
        
    def _sync_fund_info(self):
        """将 CSV 里的静态配置精准同步到 fund_info 表中"""
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        try:
            cursor = conn.cursor()
            for _, row in self.config.iterrows():
                # 精准提取 CSV 里的中文字段
                code = str(row.get('代码', '')).strip()
                name = str(row.get('名称', '')).strip()
                category = str(row.get('分类', '未分类')).strip()
                
                idx_name = str(row.get('相关指数', '-')).strip()
                idx_code = str(row.get('指数代码', '-')).strip()
                
                purchase_fee = str(row.get('申购费', '-')).strip()
                purchase_status = str(row.get('申购状态', '-')).strip()
                redemption_fee = str(row.get('赎回费', '-')).strip()
                redemption_status = str(row.get('赎回状态', '-')).strip()
                
                # 清洗空白/无效数据
                if purchase_fee.lower() == 'nan' or not purchase_fee: purchase_fee = '-'
                if purchase_status.lower() == 'nan' or not purchase_status: purchase_status = '-'
                if redemption_fee.lower() == 'nan' or not redemption_fee: redemption_fee = '-'
                if redemption_status.lower() == 'nan' or not redemption_status: redemption_status = '-'
                if idx_code.lower() == 'nan' or not idx_code: idx_code = '-'
                
                # 默认仓位比例设为 0.95 (95%)，若你的 CSV 加了"仓位"列，可在此处读取
                pos_ratio = 0.95 
                
                if code and code != 'nan':
                    cursor.execute("""
                        INSERT INTO fund_info (
                            fund_code, fund_name, category, idx_code, idx_name, 
                            pos_ratio, purchase_fee, purchase_status, redemption_fee, redemption_status
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(fund_code) DO UPDATE SET
                            fund_name = excluded.fund_name,
                            category = excluded.category,
                            idx_code = excluded.idx_code,
                            idx_name = excluded.idx_name,
                            pos_ratio = excluded.pos_ratio,
                            purchase_fee = excluded.purchase_fee,
                            purchase_status = excluded.purchase_status,
                            redemption_fee = excluded.redemption_fee,
                            redemption_status = excluded.redemption_status,
                            update_time = CURRENT_TIMESTAMP
                    """, (code, name, category, idx_code, idx_name, pos_ratio, purchase_fee, purchase_status, redemption_fee, redemption_status))
            conn.commit()
            logger.info("✅ 基金基础配置表 (fund_info) 同步完成，所有字典字段已就绪")
        except sqlite3.OperationalError as e:
            logger.error(f"同步基金基础信息时出错: {e}")
        finally:
            conn.close()

    
    def _load_config(self):
        csv_file = os.path.join(os.path.dirname(__file__), "fund_list.csv")
        try:
            df = pd.read_csv(csv_file, dtype=str)
            return df
        except Exception as e:
            logger.error(f"❌ 找不到或无法读取基金列表文件: {csv_file}, 错误: {e}")
            sys.exit(1)
            

    def _safe_save_fund_data(self, date_str, fund_code, price=None, nav=None, volume=None, shares=None):
        """安全合并保存 fund_history：保存原始成交量，不做额外计算"""
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        try:
            cursor = conn.cursor()
            
            # 使用 COALESCE 函数，保留原有非空数据
            cursor.execute("""
                INSERT INTO fund_history (date, fund_code, price, nav, volume, shares)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, fund_code) DO UPDATE SET
                    price = COALESCE(excluded.price, fund_history.price),
                    nav = COALESCE(excluded.nav, fund_history.nav),
                    volume = COALESCE(excluded.volume, fund_history.volume),
                    shares = COALESCE(excluded.shares, fund_history.shares)
            """, (date_str, fund_code, price, nav, volume, shares))
            
            # 【重要修正】折溢价率计算保留，但移到 monitor_server 中做，不在更新器里计算
            # 因为更新器里数据不一定完整
            
            conn.commit()
        except sqlite3.OperationalError as e:
            logger.error(f"数据库写入锁定/超时 [{fund_code} - {date_str}]: {e}")
        finally:
            conn.close()

    def _is_access_synced_today(self, sync_date, source):
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM access_sync_status WHERE sync_date = ? AND access_source = ?", (sync_date, source))
            result = cursor.fetchone()
            return result is not None
        finally:
            conn.close()

    def _mark_access_synced(self, sync_date, source):
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO access_sync_status (sync_date, access_source, sync_time)
                VALUES (?, ?, ?)
            """, (sync_date, source, datetime.now().strftime('%H:%M:%S')))
            conn.commit()
        finally:
            conn.close()

    def _fetch_and_save_price_data(self):
        tasks = []
        for _, row in self.config.iterrows():
            code = str(row.get('code', row.get('基金代码', row.iloc[1] if len(row)>1 else ''))).strip()
            name = str(row.get('name', row.get('基金名称', row.iloc[2] if len(row)>2 else ''))).strip()
            if code and code != 'nan':
                tasks.append((code, name))
                
        logger.info(f"📊 成功读取 {len(tasks)} 只基金配置，线程池启动...")

        def process_fund_price(code):
            price_df = data_fetcher.fetch_lof_price_data(code)
            return code, price_df

        stats = {'price_updated': 0, 'errors': 0}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_to_fund = {executor.submit(process_fund_price, task[0]): task for task in tasks}
            
            for i, future in enumerate(concurrent.futures.as_completed(future_to_fund), 1):
                code, name = future_to_fund[future]
                try:
                    _, price_df = future.result()
                    if price_df is not None and not price_df.empty:
                        stats['price_updated'] += 1
                        for _, p_row in price_df.iterrows():
                            d_str = pd.to_datetime(p_row['日期']).strftime('%Y-%m-%d')
                            self._safe_save_fund_data(date_str=d_str, fund_code=code, price=p_row['LOF交易价格'], volume=p_row.get('成交量'))
                    if i % 20 == 0 or i == len(tasks):
                        logger.info(f"价格采集进度: [{i}/{len(tasks)}]")
                except Exception as exc:
                    stats['errors'] += 1
                    logger.error(f"❌ [{i}/{len(tasks)}] {name} ({code}) 处理异常: {exc}")
        
        logger.info(f"📊 价格采集完成: 成功 {stats['price_updated']} 只, 异常 {stats['errors']} 只")

    def _fetch_and_save_nav_data(self):
        tasks = []
        for _, row in self.config.iterrows():
            code = str(row.get('code', row.get('基金代码', row.iloc[1] if len(row)>1 else ''))).strip()
            name = str(row.get('name', row.get('基金名称', row.iloc[2] if len(row)>2 else ''))).strip()
            if code and code != 'nan':
                tasks.append((code, name))

        def process_fund_nav(code):
            nav_dict = data_fetcher.fetch_lof_nav_data(code)
            
            # 只对深交所基金(15/16开头)尝试获取场内份额，其他基金跳过
            shares_info = None
            fund_code_str = str(code)
            if (fund_code_str.startswith('15') or fund_code_str.startswith('16')) and not data_fetcher._szse_blocked:
                shares_info = data_fetcher.fetch_szse_fund_shares_only(code)
            
            return code, nav_dict, shares_info

        stats = {'nav_days_saved': 0, 'shares_updated': 0, 'errors': 0}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_to_fund = {executor.submit(process_fund_nav, task[0]): task for task in tasks}
            
            for i, future in enumerate(concurrent.futures.as_completed(future_to_fund), 1):
                code, name = future_to_fund[future]
                try:
                    _, nav_dict, shares_info = future.result()

                    if isinstance(nav_dict, dict) and nav_dict:
                        for nav_date, nav_val in nav_dict.items():
                            try:
                                if nav_val is not None:
                                    self._safe_save_fund_data(date_str=str(nav_date), fund_code=code, nav=float(nav_val))
                                    stats['nav_days_saved'] += 1
                            except Exception:
                                continue

                    if shares_info and shares_info.get('shares') and shares_info.get('nav_date'):
                        stats['shares_updated'] += 1
                        self._safe_save_fund_data(
                            date_str=shares_info['nav_date'],
                            fund_code=code,
                            shares=shares_info.get('shares')
                        )

                    if i % 20 == 0 or i == len(tasks):
                        logger.info(f"净值采集进度: [{i}/{len(tasks)}]")
                except Exception as exc:
                    stats['errors'] += 1
                    logger.error(f"❌ [{i}/{len(tasks)}] {name} ({code}) 处理异常: {exc}")
        
        logger.info(f"📊 净值采集完成: 写入净值日记录 {stats['nav_days_saved']} 条, 份额更新 {stats['shares_updated']} 只, 异常 {stats['errors']} 只")

    def _fetch_tqcenter_kline(self, symbol, beg_date, end_date):
        """全新通达信 tqcenter 引擎获取历史K线"""
        try:
            from tqcenter import tq
            tq.initialize(__file__)
            
            market_sym = f"{symbol}.SZ" if str(symbol).startswith('399') else f"{symbol}.SH"
            
            df_dict = tq.get_market_data(field_list=[], stock_list=[market_sym], start_time=beg_date, end_time=end_date, count=100, period='1d')
            
            results = []
            if df_dict and 'Close' in df_dict and market_sym in df_dict['Close']:
                series = df_dict['Close'][market_sym].dropna()
                for date_idx, close_val in series.items():
                    date_str = date_idx.strftime('%Y-%m-%d') if hasattr(date_idx, 'strftime') else str(date_idx)[:10]
                    if beg_date <= date_str <= end_date:
                        results.append((date_str, float(close_val)))
            tq.close()
            return results
        except ImportError:
            logger.error("❌ 缺少 tqcenter 库")
            return None
        except Exception as e:
            logger.error(f"tqcenter获取K线失败: {symbol} {beg_date}-{end_date}, 错误: {e}")
            try: tq.close()
            except: pass
            return None

    def _get_last_index_last_date(self, symbol):
        """获取指数最后一条数据日期"""
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT date FROM index_history 
                WHERE symbol = ? 
                ORDER BY date DESC 
                LIMIT 1
            ''', (symbol,))
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            conn.close()

    def _save_index_history(self, symbol, klines):
        """保存指数历史数据"""
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        try:
            cursor = conn.cursor()
            count = 0
            for date_str, close_val in klines:
                cursor.execute('''
                    INSERT OR REPLACE INTO index_history (symbol, date, close, source)
                    VALUES (?, ?, ?, ?)
                ''', (symbol, date_str, close_val, 'eastmoney'))
                count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    def _get_market_update_time(self, symbol):
        """根据指数符号判断市场类型和收盘时间"""
        # A股：399/000开头
        if re.match(r'^399\d{3,6}$', str(symbol)) or re.match(r'^000\d{3,6}$', str(symbol)) or re.match(r'^001\d{3,6}$', str(symbol)):
            return 'A', 15, 10
        # 港股：hk前缀
        elif str(symbol).startswith('hk'):
            return 'HK', 16, 10
        # 美股：gb前缀
        elif str(symbol).startswith('gb'):
            return 'US', 4, 0
        # 默认按港股处理
        else:
            return 'HK', 16, 10

    def _should_fetch_today(self, symbol):
        """判断今天是否应该更新这个指数"""
        market_type, hour, minute = self._get_market_update_time(symbol)
        now = datetime.now()
        
        # 如果现在时间还早于收盘时间+10分钟，不更新
        if now.hour < hour or (now.hour == hour and now.minute < minute):
            return False
        
        # 暂时简化：判断是否是交易日（暂时默认今天是交易日，周末/假期暂不判断）
        return True

    def _update_index_history(self):
        """更新指数历史数据"""
        # 定义需要更新的指数配置（暂时只测试 hkHSCI）
        index_configs = [
            {'symbol': 'hkHSCI', 'secid': '124.HSCI'},
        ]
        
        total_saved = 0
        total_skipped = 0
        
        for idx, cfg in enumerate(index_configs):
            symbol = cfg['symbol']
            # secid = cfg['secid'] # TDX 不需要东财的 secid
            
            # 每个指数请求前停顿20秒（第一个不用等）
            if idx > 0:
                logger.info(f"⏸️ 停顿20秒，避免被封...")
                time.sleep(20)
            
            # 检查今天是否已同步
            today_str = datetime.now().strftime('%Y-%m-%d')
            if self._is_access_synced_today(today_str, f'index_{symbol}'):
                logger.info(f"⏭️ [{symbol}] 今日已同步，跳过")
                total_skipped += 1
                continue
            
            # 获取最后有数据的日期
            last_date = self._get_last_index_last_date(symbol)
            
            # 计算开始和结束日期
            now = datetime.now()
            end_date = now.strftime('%Y-%m-%d')
            if last_date:
                # 有历史数据：从last_date + 1天 开始
                last_dt = datetime.strptime(last_date, '%Y-%m-%d')
                beg_dt = last_dt + timedelta(days=1)
                beg_date = beg_dt.strftime('%Y-%m-%d')
                logger.info(f"🔄 [{symbol}] 从 {beg_date} 到 {end_date} 补充数据")
            else:
                # 没有历史数据：初始化过去30天
                thirty_days_ago = now - timedelta(days=30)
                beg_date = thirty_days_ago.strftime('%Y-%m-%d')
                logger.info(f"🔄 [{symbol}] 初始化从 {beg_date} 到 {end_date} (过去30天)")
            
            # 检查今天是否应该获取今天的数据
            if not self._should_fetch_today(symbol):
                logger.info(f"⏭️ [{symbol}] 现在还早，不更新今天")
                # 暂时只获取到昨天
                end_date = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            
            # 如果开始日期晚于结束日期，说明数据齐全
            if datetime.strptime(beg_date, '%Y-%m-%d') > datetime.strptime(end_date, '%Y-%m-%d'):
                logger.info(f"✅ [{symbol}] 数据齐全，无需更新")
                self._mark_access_synced(today_str, f'index_{symbol}')
                total_skipped += 1
                continue
            
            # 获取K线数据 (切换为 TDX)
            klines = self._fetch_tqcenter_kline(symbol, beg_date, end_date)
            
            if klines and len(klines) > 0:
                saved = self._save_index_history(symbol, klines)
                logger.info(f"✅ [{symbol}] 保存 {saved} 条历史数据")
                total_saved += saved
                self._mark_access_synced(today_str, f'index_{symbol}')
            else:
                logger.warning(f"⚠️ [{symbol}] 没有获取到数据")
        
        logger.info(f"📊 指数历史数据更新完成: 保存 {total_saved} 条, 跳过 {total_skipped} 个")

    def run(self):
        today = datetime.now().strftime('%Y-%m-%d')
        
        if self._is_access_synced_today(today, 'jsl_price_sina'):
            logger.info("⏭️ [防刷] 新浪财经价格今日已同步，跳过采集")
        else:
            logger.info("🔄 [防刷] 开始采集新浪财经价格数据...")
            self._fetch_and_save_price_data()
            self._mark_access_synced(today, 'jsl_price_sina')
            logger.info("✅ [防刷] 新浪财经价格数据已标记同步")
        
        if self._is_access_synced_today(today, 'jsl_nav_eastmoney'):
            logger.info("⏭️ [防刷] 东方财富净值今日已同步，跳过采集")
        else:
            logger.info("🔄 [防刷] 开始采集东财净值数据...")
            self._fetch_and_save_nav_data()
            self._mark_access_synced(today, 'jsl_nav_eastmoney')
            logger.info("✅ [防刷] 东财净值数据已标记同步")
        
        # 新增：更新指数历史数据
        logger.info("🔄 [指数] 开始更新指数历史数据...")
        self._update_index_history()
        
        logger.info("🎉 JSL看板所有基金数据更新完毕！您可以启动看板服务了。")

if __name__ == "__main__":
    JslDataUpdater().run()

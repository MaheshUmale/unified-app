
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict
from core.strategy_utils import get_5day_median_gamma, get_nifty_adv
from db.mongodb import get_db

logger = logging.getLogger(__name__)

from core import data_engine

def format_nifty_option_symbol(expiry_str: str, strike: float, option_type: str) -> str:
    """Formats Nifty option symbol as: NIFTY 50 03 FEB 2026 CALL 25300"""
    try:
        dt = datetime.strptime(expiry_str, "%Y-%m-%d")
        # Format: 03 FEB 2026
        formatted_date = dt.strftime("%d %b %Y").upper()
        # Map CE/PE to CALL/PUT if needed, but here we expect CALL/PUT as input
        return f"NIFTY 50 {formatted_date} {option_type} {int(strike)}"
    except:
        return f"NIFTY 50 {expiry_str} {option_type} {strike}"

class ATMOptionBuyingStrategy:
    def __init__(self):
        self.contexts = defaultdict(lambda: {
            "global_cues": "Neutral",
            "major_events": "None"
        })
        self.last_results = {}

    def set_context(self, symbol: str, global_cues: str, major_events: str):
        self.contexts[symbol]["global_cues"] = global_cues
        self.contexts[symbol]["major_events"] = major_events

    def fetch_market_data(self, symbol: str, index_key: str, atm_strike: int, expiry: str) -> Dict[str, Any]:
        """Fetches required data for analysis from memory and DB."""
        from external import upstox_helper

        ce_key = upstox_helper.resolve_instrument_key(symbol, 'CE', strike=float(atm_strike), expiry=expiry)
        pe_key = upstox_helper.resolve_instrument_key(symbol, 'PE', strike=float(atm_strike), expiry=expiry)

        if not ce_key or not pe_key:
            return {}

        db = get_db()
        coll = db['strike_oi_data']
        now = data_engine.get_now()

        # 15 mins ago data
        time_15m_ago = now - timedelta(minutes=15)

        def get_historical_metrics(key):
            if data_engine.replay_mode and key in data_engine.sim_strike_data:
                # Search in-memory simulation history
                history = data_engine.sim_strike_data[key]
                for doc in reversed(history):
                    if doc['updated_at'] <= time_15m_ago:
                        return doc
                return {}

            doc = coll.find_one({
                'instrument_key': key,
                'updated_at': {'$lte': time_15m_ago}
            }, sort=[('updated_at', -1)])
            return doc or {}

        def get_opening_metrics(key):
            today = now.strftime("%Y-%m-%d")
            doc = coll.find_one({
                'instrument_key': key,
                'date': today
            }, sort=[('updated_at', 1)])
            return doc or {}

        ce_hist = get_historical_metrics(ce_key)
        pe_hist = get_historical_metrics(pe_key)
        ce_open = get_opening_metrics(ce_key)
        pe_open = get_opening_metrics(pe_key)

        adv = get_nifty_adv()

        def calculate_metrics(key, opening_doc):
            ba = data_engine.latest_bid_ask.get(key, {})
            bid = ba.get('bid', 0) or 0
            ask = ba.get('ask', 0) or 0
            current_spread = abs(ask - bid) if ask and bid else 0.5

            vtt = data_engine.latest_vtt.get(key, 0) or 0
            vol_spike = vtt > (adv / 375 * 5) if adv else False

            greeks = data_engine.latest_greeks.get(key, {}) or {}

            return {
                "instrument_key": key,
                "price": data_engine.latest_prices.get(key, 0) or 0,
                "iv": data_engine.latest_iv.get(key, 0) or 0,
                "oi": data_engine.latest_oi.get(key, 0) or 0,
                "theta": greeks.get('theta', 0) or 0,
                "gamma": greeks.get('gamma', 0) or 0,
                "spread": current_spread,
                "open_spread": opening_doc.get('spread', current_spread) or current_spread,
                "vol_spike": vol_spike
            }

        ce_metrics = calculate_metrics(ce_key, ce_open)
        ce_metrics.update({
            "oi_15m_ago": ce_hist.get('oi', 0) or 0,
            "iv_15m_ago": ce_hist.get('iv', 0) or 0
        })

        pe_metrics = calculate_metrics(pe_key, pe_open)
        pe_metrics.update({
            "oi_15m_ago": pe_hist.get('oi', 0) or 0,
            "iv_15m_ago": pe_hist.get('iv', 0) or 0
        })

        data = {
            "spot_price": data_engine.latest_prices.get(index_key, 0) or 0,
            "india_vix": data_engine.latest_vix.get('value', 0) or 0,
            "atm_strike": atm_strike,
            "expiry": expiry,
            "atm_ce": ce_metrics,
            "atm_pe": pe_metrics
        }
        return data

    def analyze(self, symbol: str, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the ATM Option Buying Strategy analysis.
        """
        try:
            logger.info(f"Analyzing {symbol} strategy with market data keys: {list(market_data.keys())}")
            spot = market_data.get('spot_price', 0)
            vix = market_data.get('india_vix', 0)
            atm_strike = market_data.get('atm_strike', 0)

            ce = market_data.get('atm_ce', {})
            pe = market_data.get('atm_pe', {})

            if not ce or not pe:
                logger.warning(f"Insufficient ATM data for {symbol}: CE={bool(ce)}, PE={bool(pe)}")
                return {"error": "Insufficient ATM data"}

            logger.info(f"{symbol} ATM Data - Spot: {spot}, CE IV: {ce.get('iv')}, PE IV: {pe.get('iv')}, Straddle: {ce.get('price', 0) + pe.get('price', 0)}")

            # 1. IV VELOCITY FILTER
            ce_iv = ce.get('iv', 0) or 0
            pe_iv = pe.get('iv', 0) or 0
            ce_iv_15m = ce.get('iv_15m_ago', ce_iv) or ce_iv
            pe_iv_15m = pe.get('iv_15m_ago', pe_iv) or pe_iv

            ce_iv_vel = (ce_iv - ce_iv_15m) / 15
            pe_iv_vel = (pe_iv - pe_iv_15m) / 15

            # Normalizing daily theta to a 15-minute interval (approx 25 intervals in a 375-min Indian market day)
            ce_theta_15m = abs(ce.get('theta', 0) or 0) / 25
            pe_theta_15m = abs(pe.get('theta', 0) or 0) / 25

            filter_a_ce = ce_iv_vel > (ce_theta_15m * 0.6)
            filter_a_pe = pe_iv_vel > (pe_theta_15m * 0.6)
            filter_a = filter_a_ce or filter_a_pe

            # 2. STRADDLE-MATH FILTER
            ce_price = ce.get('price', 0) or 0
            pe_price = pe.get('price', 0) or 0
            straddle_price = ce_price + pe_price
            iv_decimal = (ce_iv + pe_iv) / 200
            expected_move_15m = spot * iv_decimal * math.sqrt(15 / 525600)
            filter_b = expected_move_15m >= (0.9 * straddle_price)

            # 3. OI-MICRO FILTER
            adv = get_nifty_adv() or 5000000
            threshold = 0.002 * adv

            ce_oi = ce.get('oi', 0) or 0
            pe_oi = pe.get('oi', 0) or 0
            ce_oi_15m = ce.get('oi_15m_ago', ce_oi) or ce_oi
            pe_oi_15m = pe.get('oi_15m_ago', pe_oi) or pe_oi

            ce_oi_change = ce_oi - ce_oi_15m
            pe_oi_change = pe_oi - pe_oi_15m

            filter_c = (abs(ce_oi_change) > threshold) or (abs(pe_oi_change) > threshold)

            # 4. GAMMA-AMPLIFICATION FILTER
            ce_gamma = ce.get('gamma', 0) or 0
            pe_gamma = pe.get('gamma', 0) or 0
            ce_gamma_median = get_5day_median_gamma(ce.get('instrument_key')) or 0
            pe_gamma_median = get_5day_median_gamma(pe.get('instrument_key')) or 0
            filter_d = (ce_gamma > ce_gamma_median) or (pe_gamma > pe_gamma_median)

            # 5. MICROSTRUCTURE FILTER
            filter_e_ce = (ce.get('spread', 999) < ce.get('open_spread', 999)) and (ce.get('vol_spike', False))
            filter_e_pe = (pe.get('spread', 999) < pe.get('open_spread', 999)) and (pe.get('vol_spike', False))
            filter_e = filter_e_ce or filter_e_pe

            # 6. TIME CUT-OFF
            now = data_engine.get_now()
            # Ensure we are checking IST hour
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            if now.tzinfo is None:
                now_ist = ist.localize(now) # Assume naive is IST or handle accordingly
            else:
                now_ist = now.astimezone(ist)

            filter_f = now_ist.hour < 14

            filters = {
                "IV_VELOCITY": filter_a,
                "STRADDLE_MATH": filter_b,
                "OI_MICRO": filter_c,
                "GAMMA_AMPLIFICATION": filter_d,
                "MICROSTRUCTURE": filter_e
            }
            logger.info(f"{symbol} Filter Results: {filters}")

            true_count = sum(1 for f in filters.values() if f)
            edge_met = true_count >= 4 and filter_f

            call_score = (int(filter_a_ce) + int(filter_b) + int(ce_oi_change > threshold) + int(ce_gamma > ce_gamma_median) + int(filter_e_ce)) * 20
            put_score = (int(filter_a_pe) + int(filter_b) + int(pe_oi_change > threshold) + int(pe_gamma > pe_gamma_median) + int(filter_e_pe)) * 20
            straddle_score = (int(filter_a) + int(filter_b) + int(filter_c) + int(filter_d) + int(filter_e)) * 20

            decision = "NO TRADE"
            if edge_met:
                if call_score > put_score and call_score >= 60: decision = "ATM CALL BUY"
                elif put_score > call_score and put_score >= 60: decision = "ATM PUT BUY"
                elif straddle_score >= 60: decision = "ATM LONG STRADDLE"

            # 4) TRADE DECISION (Detailed)
            expiry_str = market_data.get('expiry', '')
            decision_details = {
                "choice": decision,
                "suggested_strikes": [],
                "ideal_entry": "Now (Immediate Momentum)" if edge_met else "N/A",
                "max_holding": "30-45 minutes",
                "position_size": "15% of intraday risk capital",
                "stop_loss": "Spot -25 pts / Option -15%",
                "profit_rule": "Spot +50 pts / Option +35%"
            }

            if decision == "ATM CALL BUY":
                decision_details["suggested_strikes"].append(format_nifty_option_symbol(expiry_str, atm_strike, "CALL"))
            elif decision == "ATM PUT BUY":
                decision_details["suggested_strikes"].append(format_nifty_option_symbol(expiry_str, atm_strike, "PUT"))
            elif decision == "ATM LONG STRADDLE":
                decision_details["suggested_strikes"].append(format_nifty_option_symbol(expiry_str, atm_strike, "CALL"))
                decision_details["suggested_strikes"].append(format_nifty_option_symbol(expiry_str, atm_strike, "PUT"))
            elif decision == "NO TRADE":
                failed = []
                for k, v in filters.items():
                    if not v: failed.append(k)
                decision_details["failed_filters"] = failed

            # Probabilistic Expectancy Table
            expectancy = [
                {
                    "type": "CALL",
                    "win_prob": min(90, call_score + 10),
                    "req_move": round(ce.get('price', 0), 2),
                    "time": 15,
                    "exp_move": round(expected_move_15m, 2),
                    "net": round(expected_move_15m - ce.get('price', 0), 2)
                },
                {
                    "type": "PUT",
                    "win_prob": min(90, put_score + 10),
                    "req_move": round(pe.get('price', 0), 2),
                    "time": 15,
                    "exp_move": round(expected_move_15m, 2),
                    "net": round(expected_move_15m - pe.get('price', 0), 2)
                },
                {
                    "type": "STRADDLE",
                    "win_prob": min(90, straddle_score + 5),
                    "req_move": round(straddle_price, 2),
                    "time": 15,
                    "exp_move": round(expected_move_15m, 2),
                    "net": round(expected_move_15m - straddle_price, 2)
                }
            ]

            # Regime Probabilities
            regimes = {
                "Slow Range": 40 if vix < 15 else 20,
                "Compression_Expansion": 30 if expected_move_15m < (straddle_price * 0.5) else 10,
                "Fast Trend": 30 if expected_move_15m > (straddle_price * 0.8) else 50,
                "Erratic Chop": 10 if vix < 20 else 20
            }
            # Normalize to 100
            total = sum(regimes.values())
            regimes = {k: round(v/total * 100) for k, v in regimes.items()}

            results = {
                "edge_scores": {
                    "call": call_score,
                    "put": put_score,
                    "straddle": straddle_score
                },
                "filters": filters,
                "decision": decision,
                "decision_details": decision_details,
                "metrics": {
                    "vix": vix,
                    "straddle_price": straddle_price,
                    "expected_move": expected_move_15m,
                    "theta_burn_15m": ce_theta_15m + pe_theta_15m,
                    "expectancy": expectancy,
                    "regimes": regimes,
                    "shift_probs": {
                        "Slow Range": 20,
                        "Compression_Expansion": 25,
                        "Fast Trend": 40,
                        "Erratic Chop": 15
                    }
                },
                "context": self.contexts[symbol],
                "timestamp": data_engine.get_now().isoformat()
            }
            self.last_results = results
            return results
        except Exception as e:
            logger.error(f"Strategy Analysis Error: {e}")
            return {"error": str(e)}

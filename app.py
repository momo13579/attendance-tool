import streamlit as st
from datetime import datetime, timedelta

# ==========================================
# 1. 核心邏輯區
# ==========================================

def parse_time(time_str):
    if not time_str or time_str.strip() == "":
        return None
    try:
        base_date = datetime.now().date()
        # 支援全形冒號與自動去空白
        time_str = time_str.replace("：", ":").strip()
        t = datetime.strptime(time_str, "%H:%M").time()
        return datetime.combine(base_date, t)
    except ValueError:
        return None

def analyze_gap(g_start, g_end, lunch_start, lunch_end):
    """
    計算缺勤時間。
    自動扣除 12:00-13:00 的午休時間（不計入缺勤）。
    """
    if g_end <= g_start:
        return 0, []

    missing_minutes = 0
    missing_details = []
    
    # 1. 檢查午休前 (Start ~ 12:00)
    seg1_end = min(g_end, lunch_start)
    if seg1_end > g_start:
        mins = (seg1_end - g_start).total_seconds() / 60
        if mins > 0:
            missing_minutes += mins
            missing_details.append(f"{g_start.strftime('%H:%M')}~{seg1_end.strftime('%H:%M')} ({int(mins)}分)")

    # 2. 檢查午休後 (13:00 ~ End)
    seg2_start = max(g_start, lunch_end)
    if g_end > seg2_start:
        mins = (g_end - seg2_start).total_seconds() / 60
        if mins > 0:
            missing_minutes += mins
            missing_details.append(f"{seg2_start.strftime('%H:%M')}~{g_end.strftime('%H:%M')} ({int(mins)}分)")

    return missing_minutes, missing_details

def check_attendance_logic(w_in_str, w_out_str, l_start_str, l_end_str):
    base_date = datetime.now().date()
    
    # 定義標準時間錨點
    LUNCH_START = datetime.combine(base_date, datetime.strptime("12:00", "%H:%M").time())
    LUNCH_END = datetime.combine(base_date, datetime.strptime("13:00", "%H:%M").time())
    FLEX_START = datetime.combine(base_date, datetime.strptime("08:30", "%H:%M").time())
    
    # 🔥 修正：統一使用 09:30 作為最晚彈性時間，不再因為有請假就強制回 09:00
    # 除非請假本身就從 09:00 開始，那下方的 min(starts) 自然會抓到 09:00
    FLEX_LATEST = datetime.combine(base_date, datetime.strptime("09:30", "%H:%M").time())

    # 1. 解析輸入
    w_in = parse_time(w_in_str)
    w_out = parse_time(w_out_str)
    l_start = parse_time(l_start_str)
    l_end = parse_time(l_end_str)
    
    has_work = (w_in is not None and w_out is not None and w_out > w_in)
    has_leave = (l_start is not None and l_end is not None and l_end > l_start)
    
    if not has_work and not has_leave:
        return "⚠️ 請輸入時間", 0, []

    # 2. 計算「應上班時間 (Start Time)」
    starts = []
    if has_work: starts.append(max(w_in, FLEX_START))
    if has_leave: starts.append(max(l_start, FLEX_START))
    
    if not starts:
        return "⚠️ 時間輸入有誤", 0, []

    raw_start_time = min(starts)
    
    # 套用封頂規則：
    # 取 (實際最早活動時間) 與 (09:30) 的較小值
    # 如果你是 09:31 打卡，min(09:31, 09:30) = 09:30 -> 產生 1 分鐘缺口
    start_time = min(raw_start_time, FLEX_LATEST)
    
    # 計算「應下班時間」 (Start + 9小時)
    end_time = start_time + timedelta(hours=9) 
    
    # 3. 整理所有「在勤/請假」區間並合併
    segments = []
    if has_work: segments.append((w_in, w_out))
    if has_leave: segments.append((l_start, l_end))
    segments.sort(key=lambda x: x[0])
    
    merged = []
    for s in segments:
        # 只取在「應上班區間」內的有效部分
        actual_s = max(s[0], start_time)
        actual_e = min(s[1], end_time)
        
        if actual_e > actual_s:
            if not merged:
                merged.append([actual_s, actual_e])
            else:
                last_s, last_e = merged[-1]
                # 使用 <= 確保 12:31 下班接 12:31 請假能被視為連續
                if actual_s <= last_e: 
                    merged[-1][1] = max(last_e, actual_e)
                else:
                    merged.append([actual_s, actual_e])
    
    # 4. 比對缺口 (Gap Analysis)
    current = start_time
    total_missing = 0
    all_missing_details = []
    
    # 檢查每一個合併後的區間
    for seg_s, seg_e in merged:
        if current < seg_s:
            mins, details = analyze_gap(current, seg_s, LUNCH_START, LUNCH_END)
            total_missing += mins
            all_missing_details.extend(details)
        current = max(current, seg_e)
        
    # 檢查最後一段
    if current < end_time:
        mins, details = analyze_gap(current, end_time, LUNCH_START, LUNCH_END)
        total_missing += mins
        all_missing_details.extend(details)
        
    duty_minutes = 480 - total_missing
    return duty_minutes, total_missing, all_missing_details

# ==========================================
# 2. 網頁介面區
# ==========================================

st.set_page_config(page_title="考勤小工具 v3.1", page_icon="🕒")
st.title("🕒 出勤時間檢查器 v3.1")
st.write("請輸入打卡時間，系統將自動計算是否有異常。")

col1, col2 = st.columns(2)

with col1:
    st.subheader("🏢 上班打卡")
    in_work_start = st.text_input("上班時間", value="", placeholder="例如 09:00")
    in_work_end = st.text_input("下班時間", value="", placeholder="例如 18:00")

with col2:
    st.subheader("📝 請假資訊")
    in_leave_start = st.text_input("請假開始", value="", placeholder="若無請假免填")
    in_leave_end = st.text_input("請假結束", value="", placeholder="若無請假免填")

if st.button("🚀 開始檢查", type="primary"):
    if not in_work_start and not in_work_end and not in_leave_start and not in_leave_end:
        st.warning("⚠️ 請至少輸入一組時間喔！")
    else:
        duty, missing, details = check_attendance_logic(
            in_work_start, in_work_end, in_leave_start, in_leave_end
        )
        
        st.divider()

        if isinstance(duty, str):
            st.warning(duty)
        else:
            col_res1, col_res2 = st.columns(2)
            with col_res1:
                st.metric(label="有效工時", value=f"{duty:.1f} 分鐘")
            with col_res2:
                st.metric(label="缺勤時數", value=f"{missing:.1f} 分鐘")
            
            # 判斷結果 (容許極微小的浮點數誤差)
            if duty >= 479.9:
                st.success("✅ 狀態：正常 (無異常)")
            else:
                st.error(f"❌ 狀態：異常！ (未滿 8 小時)")
                
                if details:
                    st.markdown("### 🔍 偵測到以下缺勤區間：")
                    for detail in details:
                        st.write(f"🔴 **{detail}**")

st.markdown("---") 
st.markdown("""
    #### 💡 貼心提醒
    本系統計算結果僅供參考。
    - **規則更新**：統一享有 09:30 彈性時間 (除非請假開始時間早於 09:30)。
    - **午休扣除**：12:00-13:00 之缺勤不計入異常，亦不計入工時。
    
    👉 [點擊這裡查看公司請假規章](https://imo.hamastar.com.tw/FNews/Detail/140/?SN=5825&SystemModuleParameterSN=0) 
""")

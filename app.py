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
    計算缺勤時間，並自動扣除午休時間 (午休時間不算缺勤)
    """
    if g_end <= g_start:
        return 0, []

    missing_minutes = 0
    missing_details = []
    
    # 邏輯：把缺勤區間切成「午休前」與「午休後」兩段來算
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
    STANDARD_START = datetime.combine(base_date, datetime.strptime("09:00", "%H:%M").time())

    # 1. 解析輸入
    w_in = parse_time(w_in_str)
    w_out = parse_time(w_out_str)
    l_start = parse_time(l_start_str)
    l_end = parse_time(l_end_str)
    
    has_work = (w_in is not None and w_out is not None and w_out > w_in)
    has_leave = (l_start is not None and l_end is not None and l_end > l_start)
    
    if not has_work and not has_leave:
        return "⚠️ 請輸入時間", 0, [], "未知"

    # 2. 🔥 關鍵判定：決定「最晚起算時間」與「模式」
    # 如果有請假，強制回歸 09:00 標準；否則享有 09:30 彈性
    if has_leave:
        mode = "嚴格模式 (有請假，標準 09:00 起算)"
        FLEX_LATEST = STANDARD_START # 09:00
    else:
        mode = "彈性模式 (無請假，可彈性至 09:30)"
        FLEX_LATEST = datetime.combine(base_date, datetime.strptime("09:30", "%H:%M").time())

    # 3. 計算「應上班時間 (Start Time)」
    starts = []
    if has_work: starts.append(max(w_in, FLEX_START))
    if has_leave: starts.append(max(l_start, FLEX_START))
    
    # 預設起算時間 (取最早的活動時間)
    raw_start_time = min(starts)
    
    # 套用封頂規則：
    # 如果你是 09:01 打卡，但模式是「嚴格(09:00)」，這裡 min(09:01, 09:00) 會強制變成 09:00
    start_time = min(raw_start_time, FLEX_LATEST)
    
    # 計算「應下班時間」 (Start + 9小時)
    end_time = start_time + timedelta(hours=9) 
    
    # 4. 整理所有「在勤/請假」區間並合併
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
                # 🔥 修正：使用 <= 確保 12:01 下班接 12:01 請假能被視為連續
                if actual_s <= last_e: 
                    merged[-1][1] = max(last_e, actual_e)
                else:
                    merged.append([actual_s, actual_e])
    
    # 5. 比對缺口 (Gap Analysis)
    current = start_time
    total_missing = 0
    all_missing_details = []
    
    for seg_s, seg_e in merged:
        # 如果當前檢查點 < 區間開始點，代表中間有缺口
        if current < seg_s:
            mins, details = analyze_gap(current, seg_s, LUNCH_START, LUNCH_END)
            total_missing += mins
            all_missing_details.extend(details)
        # 移動檢查點到區間結束
        current = max(current, seg_e)
        
    # 檢查最後一段 (如果還沒到下班時間)
    if current < end_time:
        mins, details = analyze_gap(current, end_time, LUNCH_START, LUNCH_END)
        total_missing += mins
        all_missing_details.extend(details)
        
    duty_minutes = 480 - total_missing
    return duty_minutes, total_missing, all_missing_details, mode

# ==========================================
# 2. 網頁介面區
# ==========================================

st.set_page_config(page_title="考勤小工具", page_icon="🕒")
st.title("🕒 出勤時間檢查器")
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
        duty, missing, details, mode = check_attendance_logic(
            in_work_start, in_work_end, in_leave_start, in_leave_end
        )
        
        st.divider()
        
        # 顯示判定模式，讓使用者知道規則有沒有生效
        st.info(f"📋 判定規則：{mode}")

        if isinstance(duty, str):
            st.warning(duty)
        else:
            st.metric(label="有效工時 (分鐘)", value=f"{duty:.1f}")
            
            # 判斷結果
            # 浮點數比對可能有微小誤差，用 > 479.9 視為 480
            if duty >= 479.9:
                st.success("✅ 狀態：正常 (無異常)")
            else:
                st.error(f"❌ 狀態：異常！少 {missing:.1f} 分鐘 (未滿 8 小時)")
                
                if details:
                    st.markdown("### 🔍 偵測到以下缺勤區間：")
                    for detail in details:
                        st.write(f"🔴 **{detail}**")

st.markdown("---") 
st.markdown("""
    #### 💡 貼心提醒
    計算結果僅供參考，**請上UOF進行確認，並按公司請假規則請假**。<br>
    👉 [點擊這裡查看公司請假規章](https://imo.hamastar.com.tw/FNews/Detail/140/?SN=5825&SystemModuleParameterSN=0) 
""")

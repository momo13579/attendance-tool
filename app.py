import streamlit as st
from datetime import datetime, timedelta

# ==========================================
# 1. 核心邏輯區 (修改版：增加 09:30 封頂限制)
# ==========================================

def parse_time(time_str):
    if not time_str or time_str.strip() == "":
        return None
    try:
        base_date = datetime.now().date()
        time_str = time_str.replace("：", ":").strip()
        t = datetime.strptime(time_str, "%H:%M").time()
        return datetime.combine(base_date, t)
    except ValueError:
        return None

def analyze_gap(g_start, g_end, lunch_start, lunch_end):
    if g_end <= g_start:
        return 0, []

    missing_minutes = 0
    missing_details = []
    
    # 檢查午休前
    seg1_end = min(g_end, lunch_start)
    if seg1_end > g_start:
        mins = (seg1_end - g_start).total_seconds() / 60
        missing_minutes += mins
        missing_details.append(f"{g_start.strftime('%H:%M')}~{seg1_end.strftime('%H:%M')} ({int(mins)}分)")

    # 檢查午休後
    seg2_start = max(g_start, lunch_end)
    if g_end > seg2_start:
        mins = (g_end - seg2_start).total_seconds() / 60
        missing_minutes += mins
        missing_details.append(f"{seg2_start.strftime('%H:%M')}~{g_end.strftime('%H:%M')} ({int(mins)}分)")

    return missing_minutes, missing_details

def check_attendance_logic(w_in_str, w_out_str, l_start_str, l_end_str):
    base_date = datetime.now().date()
    LUNCH_START = datetime.combine(base_date, datetime.strptime("12:00", "%H:%M").time())
    LUNCH_END = datetime.combine(base_date, datetime.strptime("13:00", "%H:%M").time())
    FLEX_START = datetime.combine(base_date, datetime.strptime("08:30", "%H:%M").time())
    
    # 🔥🔥🔥 新增規則：彈性時間最晚只能到 09:30
    FLEX_LATEST = datetime.combine(base_date, datetime.strptime("09:00", "%H:%M").time())
    
    w_in = parse_time(w_in_str)
    w_out = parse_time(w_out_str)
    l_start = parse_time(l_start_str)
    l_end = parse_time(l_end_str)
    
    has_work = (w_in is not None and w_out is not None and w_out > w_in)
    has_leave = (l_start is not None and l_end is not None and l_end > l_start)
    
    if not has_work and not has_leave:
        return "⚠️ 請輸入時間", 0, []

    # 決定起算時間 (Start Time)
    starts = []
    if has_work: starts.append(max(w_in, FLEX_START))
    if has_leave: starts.append(max(l_start, FLEX_START))
    
    start_time = min(starts)
    
    # 🔥🔥🔥 關鍵修改：如果起算時間晚於 09:30，強制拉回 09:30
    # 這樣如果 09:31 打卡，系統就會認定你是從 09:30 開始算，產生 1 分鐘缺口
    start_time = min(start_time, FLEX_LATEST)
    
    end_time = start_time + timedelta(hours=9) 
    
    # 整理所有「在勤/請假」區間
    segments = []
    if has_work: segments.append((w_in, w_out))
    if has_leave: segments.append((l_start, l_end))
    segments.sort(key=lambda x: x[0])
    
    merged = []
    for s in segments:
        actual_s = max(s[0], start_time)
        actual_e = min(s[1], end_time)
        if actual_e > actual_s:
            if not merged:
                merged.append([actual_s, actual_e])
            else:
                last_s, last_e = merged[-1]
                if actual_s < last_e: 
                    merged[-1][1] = max(last_e, actual_e)
                else:
                    merged.append([actual_s, actual_e])
    
    current = start_time
    total_missing = 0
    all_missing_details = []
    
    for seg_s, seg_e in merged:
        if current < seg_s:
            mins, details = analyze_gap(current, seg_s, LUNCH_START, LUNCH_END)
            total_missing += mins
            all_missing_details.extend(details)
        current = max(current, seg_e)
        
    if current < end_time:
        mins, details = analyze_gap(current, end_time, LUNCH_START, LUNCH_END)
        total_missing += mins
        all_missing_details.extend(details)
        
    duty_minutes = 480 - total_missing
    return duty_minutes, total_missing, all_missing_details

# ==========================================
# 2. 網頁介面區 (已修改：清空預設值)
# ==========================================

# 設定網頁標題
st.set_page_config(page_title="考勤小工具", page_icon="🕒")
st.title("🕒 出勤時間檢查器")
st.write("請輸入打卡時間，系統將自動計算是否有異常。")

# 建立兩欄式排版
col1, col2 = st.columns(2)

with col1:
    st.subheader("🏢 上班打卡")
    # value="" 代表預設是空的
    # placeholder 只有在格子是空的時候才會顯示灰色提示字
    in_work_start = st.text_input("上班時間", value="", placeholder="例如 09:00")
    in_work_end = st.text_input("下班時間", value="", placeholder="例如 18:00")

with col2:
    st.subheader("📝 請假資訊")
    in_leave_start = st.text_input("請假開始", value="", placeholder="若無請假免填")
    in_leave_end = st.text_input("請假結束", value="", placeholder="若無請假免填")

# 按鈕與結果
if st.button("🚀 開始檢查", type="primary"):
    # 這裡加一個防呆：如果使用者什麼都沒填就按按鈕
    if not in_work_start and not in_work_end and not in_leave_start and not in_leave_end:
        st.warning("⚠️ 請至少輸入一組時間喔！")
    else:
        duty, missing, details = check_attendance_logic(
            in_work_start, in_work_end, in_leave_start, in_leave_end
        )
        
        st.divider() # 分隔線
        
        if isinstance(duty, str):
            st.warning(duty)
        else:
            st.metric(label="有效工時 (分鐘)", value=f"{duty:.1f}")
            
            if duty >= 480:
                st.success("✅ 狀態：正常 (無異常)")
            else:
                st.error(f"❌ 狀態：異常！少 {missing:.1f} 分鐘 (未滿 8 小時)")
                
                if details:
                    st.markdown("### 🔍 偵測到以下缺勤區間：")
                    for detail in details:
                        st.write(f"🔴 **{detail}**")
# 畫一條分隔線，讓版面好看一點
st.markdown("---") 

# 顯示提醒文字與連結
# [連結文字](網址) 是 Markdown 的標準寫法
st.markdown("""
    #### 💡 貼心提醒
    計算結果僅供參考，**請上UOF進行確認，並按公司請假規則請假**。
    
    👉 [點擊這裡查看公司請假規章](https://imo.hamastar.com.tw/FNews/Detail/140/?SN=5825&SystemModuleParameterSN=0) 
""")

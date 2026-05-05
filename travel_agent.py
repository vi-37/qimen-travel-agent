import os
from dotenv import load_dotenv
from textwrap import dedent
from agno.agent import Agent
from agno.run.agent import RunOutput
from agno.tools.serpapi import SerpApiTools
import streamlit as st
import re
from agno.models.deepseek import DeepSeek
from icalendar import Calendar, Event
from datetime import datetime, timedelta

# 加载 .env 文件中的环境变量
load_dotenv()

def generate_ics_content(plan_text:str, start_date: datetime = None) -> bytes:
    cal = Calendar()
    cal.add('prodid','-//AI Travel Planner//' )
    cal.add('version', '2.0')
    if start_date is None:
        start_date = datetime.today()
    day_pattern = re.compile(r'Day (\d+)[:\s]+(.*?)(?=Day \d+|$)', re.DOTALL)
    days = day_pattern.findall(plan_text)
    if not days:
        event = Event()
        event.add('summary', "Travel Itinerary")
        event.add('description', plan_text)
        event.add('dtstart', start_date.date())
        event.add('dtend', start_date.date())
        event.add("dtstamp", datetime.now())
        cal.add_component(event)  
    else:
        for day_num, day_content in days:
            day_num = int(day_num)
            current_date = start_date + timedelta(days=day_num - 1)
            event = Event()
            event.add('summary', f"Day {day_num} Itinerary")
            event.add('description', day_content.strip())
            event.add('dtstart', current_date.date())
            event.add('dtend', current_date.date())
            event.add("dtstamp", datetime.now())
            cal.add_component(event)
    return cal.to_ical()

st.set_page_config(page_title="全球智能旅行决策仪", layout="wide")
st.title("🌍 全球智能旅行决策仪")
st.caption("灵活启停奇门择吉，自动适配国内外专属地图导航")

if 'itinerary' not in st.session_state:
    st.session_state.itinerary = None

default_deepseek = os.getenv("DEEPSEEK_API_KEY", "")
default_serp = os.getenv("SERPAPI_API_KEY", "")

# 侧边栏：用来放一些设置项，让主界面更清爽
with st.sidebar:
    st.header("⚙️ 系统配置")
    api_key_input = st.text_input("DeepSeek API Key", value=default_deepseek, type="password")
    serp_api_key = st.text_input("Serp API Key", value=default_serp, type="password")
    
    st.divider()
    st.header("🔮 模式选择")
    # 核心修改 1：增加奇门遁甲的拨动开关
    use_qimen = st.toggle("启用奇门遁甲择吉", value=True, help="开启后将在行程前推演吉凶方位与吉时；关闭则仅生成常规旅行行程。")

if api_key_input and serp_api_key:
    # 1. 调研员 Agent 保持不变
    researcher = Agent(
        name="Researcher",
        role="搜索旅游目的地、活动和住宿",
        model=DeepSeek(id="deepseek-chat", api_key=api_key_input), 
        description=dedent("""你是一名世界级的旅行研究员。通过搜索分析返回最相关的结果。"""),
        instructions=[
            "针对目的地和要求，生成相关的搜索词。",
            "使用 `search_google` 搜索并分析结果。",
            "返回高质量、具体的地点、店铺和真实评价信息。",
        ],
        tools=[SerpApiTools(api_key=serp_api_key)],
        add_datetime_to_context=True,
    )

    # 核心修改 2：根据开关动态改变 Planner 的人设和指令
    planner_role = "资深旅行规划师 + 全球出行向导"
    planner_desc = "你精通全球旅行规划，能根据用户需求制定极具实操性的深度行程。"
    planner_instructions = [
        "1. 结合搜索结果生成详细行程草案。",
        "2. 将行程建议与用户的偏好深度融合。",
        # 核心修改 3：智能地图路由指令
        "3. 【智能地图规则】：请务必自行判断目的地是否在中国大陆境内。如果在中国大陆，请强制为所有地点附上【高德地图】链接（格式：https://ditu.amap.com/search?query=地点）；如果是中国大陆境外，请强制使用【Google Maps】链接（格式：https://www.google.com/maps/search/?api=1&query=地点）。绝不可混用。"
    ]

    # 如果开启了奇门，再把玄学设定加进去
    if use_qimen:
        planner_role += " + 奇门遁甲大局择吉专家"
        planner_desc += " 同时你精通奇门遁甲择吉，能根据时间范围和行进方位推演吉凶。"
        planner_instructions.insert(0, "【核心择吉】：在行程最开头设立『奇门择吉建议』板块。推演该时间范围内最适合出行的具体日期和时辰，解析对应的门、星、神、仪格局。")

    planner = Agent(
        name="Planner",
        role=planner_role,
        model=DeepSeek(id="deepseek-chat", api_key=api_key_input),
        description=dedent(planner_desc),
        instructions=planner_instructions,
        add_datetime_to_context=True,
    )

    # ---------------- 界面配置区 ----------------
    col_input1, col_input2 = st.columns(2)
    with col_input1:
        start_point = st.text_input("你的出发地", value="浙江安吉")
    with col_input2:
        destination = st.text_input("你想去哪里？", value="杭州")
        
    time_frame = st.text_input(
        "计划出行时间/范围", 
        value="本周末", 
        help="例如：本月内、下周末、5月1日早上等。"
    )
    
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        num_days = st.number_input("旅行几天？", min_value=1, max_value=30, value=3)
    with col_info2:
        preferences = st.text_area("特殊偏好（选填）", placeholder="输入你想吃的东西、想看的地方...")

    # ---------------- 运行按钮与输出区 ----------------
    if st.button("🚀 开始规划行程", use_container_width=True):
        with st.spinner("正在调研目的地与搜集最新资讯..."):
            research_results: RunOutput = researcher.run(f"Research {destination} for a {num_days} day trip, focusing on {preferences}", stream=False)
            st.write("✅ 目的地深度调研已完成")
            
        with st.spinner("正在规划专属智能行程..."):
            prompt = f"""
            出发地：{start_point}
            目的地：{destination}
            时间范围/要求：{time_frame}
            持续天数：{num_days} 天
            特殊要求：{preferences}
            研究结果：{research_results.content}
            
            请严格按照你的系统设定与地图规则，输出最终的行程指南。
            """
            
            # 如果没开奇门，在 prompt 里再次强调不要带玄学
            if not use_qimen:
                prompt += "\n注意：用户未开启玄学模式，请直接规划行程，绝对不要提及任何奇门遁甲、排盘、吉凶方位等内容。"
                
            response: RunOutput = planner.run(prompt, stream=False)
            st.session_state.itinerary = response.content
            
            st.markdown("---")
            st.write(response.content)
            
            ics_content = generate_ics_content(st.session_state.itinerary, start_date=None)
            st.download_button(
                label="📅 下载行程概览到日历 (.ics)",
                data=ics_content,
                file_name="travel_itinerary.ics",
                mime="text/calendar",
                use_container_width=True
            )

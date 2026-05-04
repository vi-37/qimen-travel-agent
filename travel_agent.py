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

st.set_page_config(page_title="奇门旅行决策仪", layout="wide")
st.title("奇门旅行决策仪 (智能择吉版)")
st.caption("给出时间框架，让 AI 为你推演吉日吉时，规划高德打卡路线")

if 'itinerary' not in st.session_state:
    st.session_state.itinerary = None

# 修改点：尝试从环境变量中获取默认值
default_deepseek = os.getenv("DEEPSEEK_API_KEY", "")
default_serp = os.getenv("SERPAPI_API_KEY", "")

# 将获取到的默认值填入输入框，如果 .env 没配好，框就是空的，仍可以手动输入
api_key_input = st.text_input("输入你的 DeepSeek API Key", value=default_deepseek, type="password")
serp_api_key = st.text_input("输入你的 Serp API Key", value=default_serp, type="password")

if api_key_input and serp_api_key:
    # 1. 调研员 Agent
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

    # 2. 规划师 Agent
    planner = Agent(
        name="Planner",
        role="资深旅行规划师 + 奇门遁甲大局择吉专家 + 国内出行向导",
        model=DeepSeek(id="deepseek-chat", api_key=api_key_input),
        description=dedent(
            """\
        你精通奇门遁甲择吉。
        如果用户提供的是宽泛的时间范围（如：本月、下周、五一期间），你需要扫描该时间段，
        根据从出发地到目标地的行进方位，为其推荐格局最佳的出行日期和具体时辰。
        """
        ),
        instructions=[
            "1. 【核心择吉】：在行程的最开头，设立一个明确的『奇门择吉建议』板块。如果你收到的是宽泛时间范围，请推荐该范围内最适合出行的具体日期和时辰（如：建议5月X日巳时出发）；解析推荐理由及当前的门、星、神、仪格局（如遇青龙返首、临生门等）。",
            "2. 如果用户给定了具体时间，直接排该时间的盘；若格局凶，推荐临近吉时。",
            "3. 结合搜索结果生成详细行程草案。",
            "4. 将玄学建议与用户的饮食偏好（如厚实口感、重芋泥、扎实司康等）融合，比如解释土属性食材与特定吉门的能量共振。",
            "5. 【强制地图规则】：所有的路线规划必须基于中国大陆情况。请为每一个推荐地点附上【高德地图】的文字搜索指引或 Web 链接（格式如：https://ditu.amap.com/search?query=地点名称），绝对不要使用 Google Maps。"
        ],
        add_datetime_to_context=True,
    )

    # ---------------- 界面配置区 ----------------
    col_input1, col_input2 = st.columns(2)
    with col_input1:
        start_point = st.text_input("你的出发地", value="浙江安吉")
    with col_input2:
        destination = st.text_input("你想去哪里？", value="杭州")
        
    time_frame = st.text_input(
        "计划出行时间范围 (越灵活越好)", 
        value="本月内找个吉日，不限具体时辰", 
        help="你可以填'本月内'、'下个周末'、'五一假期'，或者具体的'5月2日早上'，AI 会根据你的范围自动择吉。"
    )
    
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        num_days = st.number_input("旅行几天？", min_value=1, max_value=30, value=3)
    with col_info2:
        preferences = st.text_area("特殊偏好（选填）", placeholder="例如：想吃口感厚实扎实的甜品、喜欢重芋泥和流心芝士、避开网红店...")

    # ---------------- 运行按钮与输出区 ----------------
    col_btn1, col_btn2 = st.columns([1, 1])

    with col_btn1:
        if st.button("🔮 开启奇门择吉与行程规划", use_container_width=True):
            with st.spinner("正在调研目的地与挖掘宝藏店铺..."):
                research_results: RunOutput = researcher.run(f"Research {destination} for a {num_days} day trip, focusing on {preferences}", stream=False)
                st.write("✅ 目的地深度调研已完成")
                
            with st.spinner("正在推演奇门大局并规划高德路线..."):
                prompt = f"""
                出发地：{start_point}
                目的地：{destination}
                时间范围/要求：{time_frame}
                持续天数：{num_days} 天
                特殊要求：{preferences}
                研究结果：{research_results.content}
                
                请严格按照指令，先进行奇门择吉推演（确定最佳日期与时辰），再输出包含高德地图导航的深度行程。
                """
                response: RunOutput = planner.run(prompt, stream=False)
                st.session_state.itinerary = response.content
                
                st.markdown("---")
                st.write(response.content)
    
    with col_btn2:
        if st.session_state.itinerary:
            ics_content = generate_ics_content(st.session_state.itinerary, start_date=None)
            st.download_button(
                label="📅 下载行程概览到日历 (.ics)",
                data=ics_content,
                file_name="travel_itinerary.ics",
                mime="text/calendar",
                use_container_width=True
            )
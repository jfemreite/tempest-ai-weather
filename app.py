import streamlit as st
import requests
import google.generativeai as genai
import os
import datetime
import pandas as pd
import altair as alt
from dotenv import load_dotenv

# 1. Load Keys
load_dotenv()
TEMPEST_TOKEN = os.getenv("TEMPEST_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 2. Configure Gemini
if not GEMINI_API_KEY:
    st.error("Gemini Key missing.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

try:
    model = genai.GenerativeModel('gemini-2.5-flash')
except:
    model = genai.GenerativeModel('gemini-1.5-flash')

# 3. Helper Functions

def deg_to_compass(num):
    if num is None: return "Unknown"
    val = int((num / 22.5) + .5)
    arr = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return arr[(val % 16)]

def get_station_info():
    url = f"https://swd.weatherflow.com/swd/rest/stations?token={TEMPEST_TOKEN}"
    try:
        resp = requests.get(url).json()
        station = resp['stations'][0]
        return {
            "id": station['station_id'],
            "lat": station['latitude'],
            "lon": station['longitude']
        }
    except Exception as e:
        st.error(f"Error finding station: {e}")
        st.stop()

def get_tempest_forecast(station_id):
    url = f"https://swd.weatherflow.com/swd/rest/better_forecast?station_id={station_id}&units_temp=f&units_wind=mph&units_pressure=inhg&units_precip=in&units_distance=mi&token={TEMPEST_TOKEN}"
    return requests.get(url).json()

def get_nws_alerts(lat, lon):
    headers = {'User-Agent': '(my-weather-app, contact@example.com)'}
    url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
    try:
        resp = requests.get(url, headers=headers).json()
        if 'features' in resp and len(resp['features']) > 0:
            return [f['properties'] for f in resp['features']]
        return []
    except:
        return []

# --- APP SETUP ---
st.set_page_config(page_title="Tempest AI Teacher", page_icon="⛈️")
st.title("🎓 Tempest AI Meteorology Teacher")

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({"role": "assistant", "content": "I'm ready to analyze. Ask me a question, and I'll break down the science for you."})

# --- DATA FETCHING ---
try:
    if "weather_data" not in st.session_state:
        with st.spinner('Triangulating data sources...'):
            station_info = get_station_info()
            st.session_state.station_info = station_info
            st.session_state.weather_data = get_tempest_forecast(station_info['id'])
            st.session_state.alerts = get_nws_alerts(station_info['lat'], station_info['lon'])
            
            # Clear old outlook when getting new data
            if "weekly_outlook" in st.session_state:
                del st.session_state.weekly_outlook
    
    data = st.session_state.weather_data
    alerts = st.session_state.alerts

    # --- PARSING DATA ---
    current = data.get('current_conditions', {})
    
    # Dashboard Variables
    curr_cond_text = current.get('conditions', 'Unknown')
    curr_temp = current.get('air_temperature', 0.0)
    curr_hum = current.get('relative_humidity', 0.0)
    curr_wind = current.get('wind_avg', 0.0)
    curr_dir_deg = current.get('wind_direction', 0)
    curr_rain = current.get('precip_accum_local_day', 0.0)
    curr_pres = current.get('sea_level_pressure', 0.0)
    curr_trend_raw = current.get('pressure_trend', '') 
    curr_dir_cardinal = deg_to_compass(curr_dir_deg)

    # 5-Day Forecast Text (Used for both Outlook & Chat)
    daily_forecast_text = ""
    try:
        daily_data = data['forecast']['daily'][:7] 
        for day in daily_data:
            day_ts = day['day_start_local']
            day_name = datetime.datetime.fromtimestamp(day_ts).strftime('%A')
            high = day.get('air_temp_high', 'N/A')
            low = day.get('air_temp_low', 'N/A')
            cond = day.get('conditions', 'N/A')
            pop = day.get('precip_probability', 0)
            daily_forecast_text += f"- {day_name}: High {high}F, Low {low}F, {cond} ({pop}% Rain Chance)\n"
    except:
        daily_forecast_text = "Forecast data unavailable."

    # --- DASHBOARD UI ---
    
    # Alerts (Minimizable by default)
    if alerts:
        for alert in alerts:
            severity = alert.get('severity', 'Unknown')
            event_name = alert.get('event', 'Weather Alert')
            with st.expander(f"⚠️ ACTIVE ALERT: {event_name} ({severity})", expanded=False):
                st.write(f"**Source:** {alert.get('senderName')}")
                st.error(alert.get('description'))
    
    # Metrics Grid
    trend_delta = None
    if curr_trend_raw:
        if curr_trend_raw.lower() == 'falling':
            trend_delta = f"- {curr_trend_raw.capitalize()}" 
        elif curr_trend_raw.lower() == 'rising':
            trend_delta = f"+ {curr_trend_raw.capitalize()}" 
        else:
            trend_delta = curr_trend_raw.capitalize() 

    with st.container():
        col1, col2, col3 = st.columns(3)
        col1.metric("Condition", curr_cond_text)
        col2.metric("Temperature", f"{curr_temp:.1f}°F")
        col3.metric("Humidity", f"{curr_hum}%")

        col4, col5, col6 = st.columns(3)
        col4.metric("Pressure", f"{curr_pres:.2f} inHg", delta=trend_delta)
        col5.metric("Wind", f"{curr_wind:.1f} mph ({curr_dir_cardinal})")
        col6.metric("Rain Today", f"{curr_rain:.2f} in")
    
    st.divider()

    # --- NEW SECTION: 24-HOUR TRENDS ---
    # We use st.expander to make it collapsible ("Minimizable")
    with st.expander("📈 24-Hour Trends (Temperature & Rain)", expanded=True):
        try:
            # 1. Prepare Data for Chart
            hourly_data = data['forecast']['hourly']
            
            # Create a simplified list of dictionaries for the dataframe
            chart_data = []
            for hour in hourly_data:
                # Calculate readable time (e.g., "2 PM")
                ts = hour['time']
                local_time = datetime.datetime.fromtimestamp(ts).strftime('%I %p')
                
                chart_data.append({
                    "Time": local_time,
                    "Temperature (°F)": hour['air_temperature'],
                    "Rain Chance (%)": hour['precip_probability'],
                    "Timestamp": ts # Helper for sorting
                })
            
            # Convert to Pandas DataFrame
            df = pd.DataFrame(chart_data)

            # 2. Build the Dual-Axis Chart using Altair
            base = alt.Chart(df).encode(
                x=alt.X('Time', sort=None) # Keep order as is
            )

            # Layer 1: Temperature Line (Red)
            line = base.mark_line(color='#FF5733').encode(
                y=alt.Y('Temperature (°F)', axis=alt.Axis(title='Temp (°F)', titleColor='#FF5733'))
            )

            # Layer 2: Rain Area (Blue)
            area = base.mark_area(opacity=0.3, color='#337DFF').encode(
                y=alt.Y('Rain Chance (%)', axis=alt.Axis(title='Rain Prob (%)', titleColor='#337DFF'))
            )

            # Combine them
            chart = alt.layer(area, line).resolve_scale(
                y='independent' # Allows two different Y-axes
            )

            st.altair_chart(chart, use_container_width=True)
            
        except Exception as e:
            st.error(f"Could not load chart data: {e}")

    # --- AI WEEKLY OUTLOOK (Minimizable) ---
    # We moved this into an expander too for better organization
    with st.expander("📅 AI Weekly Strategy", expanded=False):
        
        if "weekly_outlook" not in st.session_state:
            with st.spinner("Analyzing the week ahead..."):
                outlook_prompt = f"""
                Act as a Weather Strategist.
                Here is the 7-day forecast:
                {daily_forecast_text}
                
                Write a "Weekly Outlook" for the user.
                1. **Headline:** A 4-6 word summary of the week.
                2. **Trend:** Are we warming up or cooling down?
                3. **Key Days:** Mention specific days to watch out for.
                4. **Advice:** One practical tip.
                
                Keep it concise and formatted with Markdown.
                """
                outlook_response = model.generate_content(outlook_prompt)
                st.session_state.weekly_outlook = outlook_response.text

        st.info(st.session_state.weekly_outlook)

    st.divider()

    # --- CHAT INTERFACE ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask a question..."):
        
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # --- TEACHER PROMPT ---
        alert_text = "NO ACTIVE ALERTS."
        if alerts:
            alert_text = f"ACTIVE GOVERNMENT ALERTS: {[a['event'] for a in alerts]}."

        system_context = f"""
        Act as a Meteorology Professor.
        
        LIVE DATA:
        - Pressure: {curr_pres} inHg ({curr_trend_raw})
        - Humidity: {curr_hum}%
        - Temp: {curr_temp} F
        - Wind: {curr_wind} mph (from {curr_dir_cardinal})
        - Rain Today: {curr_rain} inches
        
        ALERTS: {alert_text}
        
        FORECAST:
        {daily_forecast_text}
        
        USER QUESTION: "{prompt}"
        
        FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
        
        **The Short Answer**
        [Direct answer]
        
        **The Science Breakdown**
        * **Observation:** [Data point used] [Source: Sensor]
        * **Concept:** [Explain the concept]
        * **Prediction:** [Implication] [Source: AI Model]
        """

        with st.chat_message("assistant"):
            with st.spinner("Consulting NWS data..."):
                response = model.generate_content(system_context)
                st.markdown(response.text)
                
        st.session_state.messages.append({"role": "assistant", "content": response.text})

    if st.button("Refresh Data"):
        if "weather_data" in st.session_state:
            del st.session_state.weather_data
        if "weekly_outlook" in st.session_state:
            del st.session_state.weekly_outlook
        st.rerun()
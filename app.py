import streamlit as st
import requests
import google.generativeai as genai
import os
import datetime
import time
import pandas as pd
import altair as alt
from dotenv import load_dotenv
from zoneinfo import ZoneInfo 

# 1. Load Keys
load_dotenv()
TEMPEST_TOKEN = os.getenv("TEMPEST_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 2. Configure Gemini
if not GEMINI_API_KEY:
    st.error("Gemini Key missing.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# --- SMART FALLBACK FUNCTION (UPDATED) ---
def ask_gemini_smartly(prompt_text):
    """
    Tries to get an answer from a list of models.
    If the first one is 'tired' (Quota Limit), it tries the next one.
    """
    # User-defined model priority list
    models_to_try = [
        'gemini-2.5-flash-lite', 
        'gemini-2.5-flash', 
        'gemini-3-flash'
    ]
    
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt_text)
            return response.text # Success! Return the text.
        except Exception:
            continue # Failed? Just try the next loop.
            
    return None # If all models failed.

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
st.set_page_config(page_title="Ramsey Ct. Weather", page_icon="☁️")

# --- HEADER WITH LOGO ---
col1, col2 = st.columns([1, 5]) 

with col1:
    if os.path.exists("ramseyct.jpg"):
        st.image("ramseyct.jpg", width=100) 
    else:
        st.header("☁️") 

with col2:
    st.title("Ramsey Ct. Weather")
    st.caption("Culdesac Weather App") 

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({"role": "assistant", "content": "I'm monitoring Ramsey Ct. conditions. Ask me anything!"})

# --- DATA FETCHING ---
try:
    if "weather_data" not in st.session_state:
        with st.spinner('Updating Ramsey Ct. data...'):
            station_info = get_station_info()
            st.session_state.station_info = station_info
            st.session_state.weather_data = get_tempest_forecast(station_info['id'])
            st.session_state.alerts = get_nws_alerts(station_info['lat'], station_info['lon'])
            
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

    # 5-Day Forecast Text
    daily_forecast_text = ""
    try:
        daily_data = data['forecast']['daily'][:7] 
        for day in daily_data:
            day_ts = day['day_start_local']
            day_dt = datetime.datetime.fromtimestamp(day_ts, ZoneInfo("US/Pacific"))
            day_name = day_dt.strftime('%A')
            
            high = day.get('air_temp_high', 'N/A')
            low = day.get('air_temp_low', 'N/A')
            cond = day.get('conditions', 'N/A')
            pop = day.get('precip_probability', 0)
            daily_forecast_text += f"- {day_name}: High {high}F, Low {low}F, {cond} ({pop}% Rain Chance)\n"
    except:
        daily_forecast_text = "Forecast data unavailable."

    # --- DASHBOARD UI ---
    
    if alerts:
        for alert in alerts:
            severity = alert.get('severity', 'Unknown')
            event_name = alert.get('event', 'Weather Alert')
            with st.expander(f"⚠️ ACTIVE ALERT: {event_name} ({severity})", expanded=False):
                st.write(f"**Source:** {alert.get('senderName')}")
                st.error(alert.get('description'))
    
    # Metrics Grid
    st.subheader("Current Conditions") 
    
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

    # --- AI WEEKLY OUTLOOK (With Smart Fallback) ---
    ai_outlook_content = None
    
    if "weekly_outlook" in st.session_state:
        ai_outlook_content = st.session_state.weekly_outlook
    else:
        # Use our new fallback function
        outlook_prompt = f"""
        Act as a Weather Strategist for a home called "Ramsey Ct".
        Here is the 7-day forecast:
        {daily_forecast_text}
        
        Write a "Weekly Outlook" for the user.
        1. **Headline:** A 4-6 word summary of the week.
        2. **Trend:** Are we warming up or cooling down?
        3. **Key Days:** Mention specific days to watch out for.
        4. **Advice:** One practical tip.
        
        Keep it concise and formatted with Markdown.
        """
        response_text = ask_gemini_smartly(outlook_prompt)
        
        if response_text:
            st.session_state.weekly_outlook = response_text
            ai_outlook_content = response_text

    if ai_outlook_content:
        with st.expander("📅 AI Weekly Strategy", expanded=True): 
            st.info(ai_outlook_content)

    # --- 24-HOUR TRENDS ---
    with st.expander("📈 24-Hour Trends", expanded=True): 
        try:
            raw_hourly = data['forecast']['hourly']
            current_time_epoch = time.time()
            future_hourly = [h for h in raw_hourly if h['time'] > current_time_epoch]
            chart_slice = future_hourly[:24]
            
            chart_data = []
            for hour in chart_slice:
                ts = hour['time']
                dt_object = datetime.datetime.fromtimestamp(ts, ZoneInfo("US/Pacific"))
                
                chart_data.append({
                    "Time": dt_object, 
                    "Temperature": hour['air_temperature'],
                    "Rain Chance": hour['precip_probability']
                })
            
            df = pd.DataFrame(chart_data)
            df = df.sort_values("Time")

            # CHART 1: Temperature
            st.subheader("Temperature (°F)")
            temp_chart = alt.Chart(df).mark_line(color='#FF5733').encode(
                x=alt.X('Time:T', axis=alt.Axis(format='%a %I %p'), title="Time (PST)"),
                y=alt.Y('Temperature', scale=alt.Scale(zero=False), title="Temp (°F)"),
                tooltip=[alt.Tooltip('Time:T', format='%a %I %p'), 'Temperature']
            ).properties(height=200)
            st.altair_chart(temp_chart, use_container_width=True)

            # CHART 2: Rain Probability
            st.subheader("Rain Probability (%)")
            rain_chart = alt.Chart(df).mark_bar(color='#337DFF').encode(
                x=alt.X('Time:T', axis=alt.Axis(format='%a %I %p'), title="Time (PST)"),
                y=alt.Y('Rain Chance', scale=alt.Scale(domain=[0, 100]), title="Probability (%)"),
                tooltip=[alt.Tooltip('Time:T', format='%a %I %p'), 'Rain Chance']
            ).properties(height=200)
            st.altair_chart(rain_chart, use_container_width=True)
            
        except Exception as e:
            st.error(f"Could not load chart data: {e}")

    st.divider()

    # --- CHAT INTERFACE ---
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask about the weather..."):
        
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        system_context = f"""
        Act as a Meteorology Professor for Ramsey Ct.
        LIVE DATA:
        - Pressure: {curr_pres} inHg ({curr_trend_raw})
        - Humidity: {curr_hum}%
        - Temp: {curr_temp} F
        - Wind: {curr_wind} mph (from {curr_dir_cardinal})
        - Rain Today: {curr_rain} inches
        FORECAST:
        {daily_forecast_text}
        USER QUESTION: "{prompt}"
        """

        with st.chat_message("assistant"):
            with st.spinner("Consulting NWS data..."):
                response_text = ask_gemini_smartly(system_context)
                
                if response_text:
                    st.markdown(response_text)
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                else:
                    fallback = "I'm currently resting (All API Models Busy). Please check back in a minute!"
                    st.warning(fallback)
                    st.session_state.messages.append({"role": "assistant", "content": fallback})

    if st.button("Refresh Data"):
        if "weather_data" in st.session_state:
            del st.session_state.weather_data
        if "weekly_outlook" in st.session_state:
            del st.session_state.weekly_outlook
        st.rerun()

except Exception as e:
    st.error(f"Error: {e}")
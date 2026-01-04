import streamlit as st
import numpy as np
import plotly.graph_objects as go
from scipy.signal import find_peaks, welch
from dataclasses import dataclass

# =========================================================
# ☆ CONFIG
# =========================================================
FS = 100  # Hz
np.random.seed(42)

# =========================================================
# ☆ DATA MODELS
# =========================================================
@dataclass
class UserProfile:
    gender: str  # 'male' | 'female'
    cycle_day: int = None  # 1-28 for female

@dataclass
class VitalState:
    hr: float
    rmssd: float
    lf_hf: float
    stress: float
    power_mode: str
    cycle_phase: str = None

# =========================================================
# ☆ PPG SIMULATOR (FIXED HRV)
# =========================================================
def simulate_ppg(duration=30, hr=75, stress_level=0.3):
    ibi = 60 / hr
    rr_variation = 0.03 + stress_level * 0.07  # ⭐ FIX HRV
    beats = np.cumsum(np.random.normal(ibi, ibi * rr_variation, int(duration / ibi + 2)))
    beats = beats[beats < duration]
    t = np.linspace(0, duration, int(FS * duration))
    signal = np.zeros_like(t)
    for bt in beats:
        idx = int(bt * FS)
        if idx < len(signal):
            signal[idx] = 1
    kernel = np.exp(-np.linspace(0, 1, 50))
    ppg = np.convolve(signal, kernel, mode="same")
    noise = np.random.normal(0, 0.01 + stress_level * 0.02, len(ppg))
    return ppg + noise, t

# =========================================================
# ☆ SIGNAL PROCESSING
# =========================================================
def extract_peaks(ppg):
    peaks, _ = find_peaks(ppg, distance=FS * 0.4, prominence=0.05)
    return peaks

def compute_hr(peaks):
    if len(peaks) < 2:
        return 0
    rr = np.diff(peaks) / FS
    return 60 / np.mean(rr)

def compute_rmssd(peaks):
    if len(peaks) < 3:
        return 0.0
    rr = np.diff(peaks) / FS
    diff_rr = np.diff(rr)
    return float(np.sqrt(np.mean(diff_rr**2)) * 1000)  # ms

def compute_lf_hf(peaks):
    # بررسی تعداد پیک‌ها و RR intervals
    if len(peaks) < 8:
        return 0.0  # تعداد پیک‌ها کافی نیست

    rr = np.diff(peaks) / FS
    rr -= np.mean(rr)  # حذف میانگین از RR intervals
    fs_rr = 1 / np.mean(rr)  # تنظیم نرخ نمونه‌برداری
    try:
        # انجام Welch روی RR intervals برای محاسبه LF/HF
        f, pxx = welch(rr, fs=fs_rr, nperseg=min(256, len(rr)))
        lf = np.trapz(pxx[(f >= 0.04) & (f <= 0.15)])  # LF band
        hf = np.trapz(pxx[(f >= 0.15) & (f <= 0.4)])  # HF band
        return float(lf / hf) if hf > 1e-6 else 0.0  # اگر HF کمتر از مقدار آستانه باشد، مقدار 0 برمی‌گرداند
    except Exception as e:
        return 0.0  # در صورت بروز خطا، مقدار پیش‌فرض 0 برگشت داده می‌شود

# =========================================================
# ☆ FEMALE CYCLE ENGINE
# =========================================================
def cycle_phase(day):
    if day <= 5:
        return "MENSTRUAL"
    elif day <= 13:
        return "FOLLICULAR"
    elif day <= 16:
        return "OVULATORY"
    else:
        return "LUTEAL"

def cycle_modifier(phase):
    return {
        "MENSTRUAL": -0.1,
        "FOLLICULAR": 0.0,
        "OVULATORY": 0.1,
        "LUTEAL": 0.15
    }.get(phase, 0)

# =========================================================
# ☆ STRESS & POWER AI AGENT
# =========================================================
def estimate_stress(hr, rmssd, lf_hf, circadian_factor):
    hrv_score = np.clip((80 - rmssd) / 80, 0, 1)  # مقیاس دقیق‌تر برای RMSSD
    hr_score = np.clip((hr - 60) / 60, 0, 1)
    lf_hf_score = np.clip(lf_hf / 2, 0, 1)
    stress = (
        0.4 * hrv_score +
        0.3 * hr_score +
        0.2 * lf_hf_score +
        0.1 * circadian_factor
    )
    return np.clip(stress, 0, 1)

def power_manager(stress, hr):
    if stress < 0.25 and hr < 85:
        return "LOW_POWER"
    elif stress < 0.6:
        return "NORMAL"
    else:
        return "HIGH_FIDELITY"

# =========================================================
# ☆ CIRCARDIAN ENGINE
# =========================================================
def circadian_factor(hour):
    """محاسبه فاکتور شبانه‌روزی"""
    return 0.2 if hour < 6 or hour > 22 else 0

# =========================================================
# ☆ KIVARA AGENT (MASTER)
# =========================================================
class KivaraAgent:
    def __init__(self, gender="M", cycle_day=1, baseline_hr=75.0, baseline_rmssd=45.0):
        self.gender = gender.upper()
        self.cycle_day = cycle_day
        self.baseline_hr = baseline_hr
        self.baseline_rmssd = baseline_rmssd
        self.stress_history = []
        self.anomaly = 0.0
        self.power_mode = "NORMAL"
        self.device_state = "ACTIVE"  # حالت اولیه دستگاه به عنوان فعال

    def update_cycle_factor(self):
        """محاسبه فاکتور چرخه قاعدگی برای خانم‌ها"""
        if self.gender != "F": return 1.0
        d = self.cycle_day
        if d <= 5: return 0.7  # فاز قاعدگی
        if 6 <= d <= 13: return 1.0  # فاز فولیکولی
        if 14 <= d <= 16: return 1.35  # فاز تخمک‌گذاری
        return 0.9  # فاز لوتئال

    def estimate_stress(self, hr, rmssd, lf_hf, circadian_factor):
        """تخمین سطح استرس بر اساس HR، RMSSD، LF/HF و فاکتور شبانه‌روزی"""
        hrv_score = np.clip((80 - rmssd) / 80, 0, 1)
        hr_score = np.clip((hr - 60) / 60, 0, 1)
        lf_hf_score = np.clip(lf_hf / 2, 0, 1)
        stress = (
            0.4 * hrv_score +
            0.3 * hr_score +
            0.2 * lf_hf_score +
            0.1 * circadian_factor
        )
        return np.clip(stress, 0, 1)

    def power_manager(self, stress, hr):
        """مدیریت مصرف انرژی دستگاه بر اساس سطح استرس و HR"""
        if stress < 0.25 and hr < 85:
            return "LOW_POWER"
        elif stress < 0.6:
            return "NORMAL"
        else:
            return "HIGH_FIDELITY"

    def device_control(self, power_mode):
        """کنترل وضعیت دستگاه بر اساس قدرت مصرفی"""
        if power_mode == "LOW_POWER":
            self.device_state = "SLEEP"  # دستگاه در حالت خواب یا کم مصرف قرار می‌گیرد
        elif power_mode == "NORMAL":
            self.device_state = "ACTIVE"  # دستگاه فعال است
        elif power_mode == "HIGH_FIDELITY":
            self.device_state = "BOOST"  # دستگاه در حالت قدرت بالا یا وضوح بالا قرار می‌گیرد
        else:
            self.device_state = "ERROR"  # اگر وضعیت شناخته نشده باشد، به حالت خطا می‌رود

    def analyze(self, ppg, circadian_hour):
        """تحلیل سیگنال‌های PPG، محاسبه HR، RMSSD، LF/HF و تصمیم‌گیری در مورد وضعیت دستگاه"""
        peaks = extract_peaks(ppg)
        hr = compute_hr(peaks)
        rmssd = compute_rmssd(peaks)
        lf_hf = compute_lf_hf(peaks)
        circadian_factor_value = circadian_factor(circadian_hour)
        
        # تخمین سطح استرس و انتخاب Power Mode
        stress = self.estimate_stress(hr, rmssd, lf_hf, circadian_factor_value)
        self.power_mode = self.power_manager(stress, hr)
        
        # کنترل دستگاه بر اساس وضعیت Power Mode
        self.device_control(self.power_mode)
        
        # تاریخچه استرس را به‌روزرسانی می‌کنیم
        self.stress_history.append(stress)
        if len(self.stress_history) > 10:
            self.stress_history.pop(0)
        
        return {
            "hr": round(hr, 1),
            "rmssd": round(rmssd, 1),
            "lf_hf": round(lf_hf, 2),
            "stress": round(stress, 2),
            "power_mode": self.power_mode,
            "device_state": self.device_state
        }

# =========================================================
# ☆ STREAMLIT DEMO
# =========================================================
st.set_page_config(page_title="KIVARA: Physiological AI Agent", page_icon="🌿", layout="wide")

# User Inputs for Gender, Cycle Day, and Stress Level
st.title("🌿 KIVARA: Physiological AI Agent Demo 🚀")

# Add Stickers to make UI engaging
st.markdown("### Select your parameters to analyze your stress levels 🌱")

gender = st.selectbox("Select Gender 🧑‍⚕️", ["male", "female"])
cycle_day = st.slider("Cycle Day", 1, 28, 14) if gender == "female" else None
stress_level = st.slider("Stress Level 😨", 0.0, 1.0, 0.5)
hr = st.slider("Heart Rate (HR) 💓", 50, 150, 75)

# Simulate PPG Signal
ppg, t = simulate_ppg(hr=hr, stress_level=stress_level)

# Create KivaraAgent
agent = KivaraAgent(gender=gender, cycle_day=cycle_day if gender == "female" else 1)

# Analyze PPG and Display Results
result = agent.analyze(ppg, circadian_hour=14)

# Display Results with stickers
st.subheader("Physiological Data Analysis 🧠🌿")

# Show metrics
col1, col2, col3 = st.columns(3)
col1.metric("Heart Rate (HR) 💓", f"{result['hr']} bpm")
col2.metric("RMSSD 🧘‍♂️", f"{result['rmssd']} ms")
col3.metric("LF/HF ⚖️", f"{result['lf_hf']}")

# Show stress level and power mode
col4, col5 = st.columns(2)
col4.metric("Stress Level 🆘", f"{result['stress']:.2f}")
col5.metric("Power Mode ⚡", result["power_mode"])

# Device state
st.write(f"Device State: {result['device_state']} 🟢")

# Plot PPG signal
st.subheader("PPG Signal Visualization 📊")
fig = go.Figure()
fig.add_trace(go.Scatter(x=t, y=ppg, mode='lines', name="Simulated PPG Signal"))
fig.update_layout(title="Simulated PPG Signal", xaxis_title="Time (seconds)", yaxis_title="Amplitude")
st.plotly_chart(fig)

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
    print(f"Number of peaks: {len(peaks)}")  # تعداد پیک‌ها چاپ می‌شود
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
        print(f"LF: {lf}, HF: {hf}")  # چاپ مقدار LF و HF برای بررسی
        return float(lf / hf) if hf > 1e-6 else 0.0
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
        self.baseline_hr = baselin_

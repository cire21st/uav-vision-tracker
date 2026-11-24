"""Plot auto.cpp's mapping using numeric constants from the current config.h."""
import json
from pathlib import Path
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / 'firmware/motor_control/Core/Inc/config.h'
OUT = ROOT / 'outputs/auto_rpm_mapping'


def constants():
    text = CONFIG.read_text(encoding='utf-8')
    names = ('AUTO_DEADBAND', 'VISION_FRAME_WIDTH', 'VISION_FRAME_HEIGHT',
             'AUTO_PAN_MAX_RPM', 'AUTO_TILT_MAX_RPM', 'AUTO_MOTOR_MAX_RPM')
    return {name: float(re.findall(r'^#define\s+' + name + r'\s+(\d+)\s*$',
                                  text, re.MULTILINE)[-1]) for name in names}


def mapping(dx, dy, c):
    def normalize(error, half_size):
        return np.where(np.abs(error) <= c['AUTO_DEADBAND'], 0,
                        np.clip(np.asarray(error) / half_size, -1, 1))
    pan = -c['AUTO_PAN_MAX_RPM'] * normalize(dx, c['VISION_FRAME_WIDTH'] / 2)
    tilt = c['AUTO_TILT_MAX_RPM'] * normalize(dy, c['VISION_FRAME_HEIGHT'] / 2)
    raw1, raw2 = pan, pan + tilt
    peak = np.maximum(np.abs(raw1), np.abs(raw2))
    scale = np.minimum(1, c['AUTO_MOTOR_MAX_RPM'] / np.maximum(peak, 1e-12))
    def roundf(v):
        return np.sign(v) * np.floor(np.abs(v) + 0.5)
    return roundf(raw1 * scale), roundf(raw2 * scale), peak


def main():
    c = constants()
    OUT.mkdir(parents=True, exist_ok=True)
    hw, hh = int(c['VISION_FRAME_WIDTH'] / 2), int(c['VISION_FRAME_HEIGHT'] / 2)
    x, y = np.arange(-hw, hw + 1), np.arange(-hh, hh + 1)
    xx, yy = np.meshgrid(x, y)
    m1, m2, peak = mapping(xx, yy, c)
    limit = c['AUTO_MOTOR_MAX_RPM']
    assert max(np.abs(m1).max(), np.abs(m2).max()) <= limit
    assert mapping(10, -10, c)[:2] == (0, 0)
    assert mapping(-hw, hh, c)[:2] == (50, 100)
    assert mapping(hw, hh, c)[:2] == (-100, 0)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), layout='constrained')
    ax = axes[0, 0]
    a, b, _ = mapping(x, 0, c)
    ax.plot(x, a, lw=2, label='Motor 1 = Motor 2 (rounded command)')
    ax.plot(x, -c['AUTO_PAN_MAX_RPM'] * x / hw, '--', color='gray',
            alpha=0.6, label='Unmodified linear PAN')
    ax.set(title='Horizontal error only (dy = 0)', xlabel='dx (pixels; right +)', ylabel='RPM')
    ax = axes[0, 1]
    a, b, _ = mapping(0, y, c)
    ax.plot(y, b, lw=2, color='#e67e22', label='Motor 2 = TILT (rounded command)')
    ax.plot(y, a, lw=2, color='#2573ab', label='Motor 1 = 0')
    ax.set(title='Vertical error only (dx = 0)', xlabel='dy (control pixels; up +)', ylabel='RPM')
    for ax in axes[0]:
        ax.axvspan(-c['AUTO_DEADBAND'], c['AUTO_DEADBAND'], alpha=0.2,
                   color='green', label='Deadband: +/-10 px')
        ax.axhline(0, color='black', lw=0.5)
        ax.set_ylim(-limit * 1.1, limit * 1.1)
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    for ax, values, name in zip(axes[1], (m1, m2), ('Motor 1', 'Motor 2')):
        image = ax.imshow(values, extent=(-hw, hw, -hh, hh), origin='lower',
                          aspect='auto', cmap='RdBu_r', vmin=-limit, vmax=limit)
        ax.contour(xx, yy, peak, levels=[limit + 0.001], colors='black', linewidths=1)
        ax.set(title=f'{name}: combined dx/dy, after shared limit + rounding',
               xlabel='dx (pixels; right +)', ylabel='dy (control pixels; up +)')
        fig.colorbar(image, ax=ax, label='Command RPM')
    fig.suptitle('AUTO motor RPM mapping | flag = 1 | 1280 x 720\n'
                 'Black boundary: shared speed scaling begins; dy is inverted from image coordinates',
                 fontsize=14)
    fig.savefig(OUT / 'auto_rpm_mapping.png', dpi=170)
    fig.savefig(OUT / 'auto_rpm_mapping.svg')
    plt.close(fig)
    cases = []
    for dx, dy in [(0, 0), (10, 10), (11, 11), (320, 0), (0, 180),
                   (-640, 360), (640, 360), (640, -360)]:
        a, b, _ = mapping(dx, dy, c)
        cases.append(dict(dx=dx, dy=dy, motor1_rpm=int(a), motor2_rpm=int(b)))
    (OUT / 'mapping.json').write_text(json.dumps(dict(constants=c, examples=cases), indent=2))
    print(json.dumps(cases, indent=2))


if __name__ == '__main__':
    main()

"""Plot pixel observations; preserve all samples and their session identity."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('samples', type=Path, nargs='+')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    groups, combined, records = [], [], []
    dimensions = set()
    for index, path in enumerate(args.samples):
        samples = json.loads(path.read_text(encoding='utf-8'))
        if not samples:
            raise ValueError(f'Empty sample list: {path}')
        for sample in samples:
            dimensions.add((sample['width'], sample['height'],
                            sample['center_x'], sample['center_y']))
            assert sample['delta_x'] == sample['selected_x'] - sample['center_x']
            assert sample['delta_y'] == sample['selected_y'] - sample['center_y']
        values = np.array([[s['delta_x'], s['delta_y']] for s in samples], dtype=float)
        name = chr(ord('A') + index)
        groups.append((name, path, values))
        combined.extend(values)
        records.extend(dict(session=name, sample_number=i + 1, **s)
                       for i, s in enumerate(samples))
    if len(dimensions) != 1:
        raise ValueError('Samples use different resolutions or center pixels')
    values = np.array(combined)
    mean, median = values.mean(0), np.median(values, axis=0)
    std = values.std(0, ddof=1)
    width, height, cx, cy = next(iter(dimensions))
    report = dict(
        count=len(values), image_size=[width, height], center_pixel=[cx, cy],
        delta_convention='selected minus center; +x right; +y down',
        mean_delta=mean.tolist(), median_delta=median.tolist(),
        sample_std_delta=std.tolist(),
        mean_pixel=(mean + [cx, cy]).tolist(),
        rounded_mean_delta=np.rint(mean).astype(int).tolist(),
        sessions=[dict(label=name, source=str(path.resolve()), count=len(v),
                       mean_delta=v.mean(0).tolist(), sample_std_delta=v.std(0, ddof=1).tolist())
                  for name, path, v in groups])
    for filename, data in [('summary.json', report), ('combined_samples.json', records)]:
        (args.output_dir / filename).write_text(json.dumps(data, indent=2), encoding='utf-8')

    fig, ax = plt.subplots(figsize=(10, 9), layout='constrained')
    colors = ['#1674c5', '#ef7d16']
    for i, (name, path, v) in enumerate(groups):
        color = colors[i % len(colors)]
        ax.scatter(v[:, 0], v[:, 1], s=85, color=color, edgecolors='white',
                   linewidth=0.8, label=f'{name}: {path.parent.name} (n={len(v)})', zorder=4)
        label_y = -float('inf')
        for j in np.argsort(v[:, 1], kind='stable'):
            x, y = v[j]
            label_y = max(y, label_y + 8)
            ax.annotate(f'{name}{j + 1}', (x, y),
                        xytext=(55 if i % 2 == 0 else 150, label_y),
                        ha='right' if i % 2 == 0 else 'left', va='center',
                        fontsize=9, color=color,
                        arrowprops=dict(arrowstyle='-', color=color, lw=0.6, alpha=0.65))
    ax.axhline(0, color='#888888', lw=1)
    ax.axvline(0, color='#888888', lw=1)
    ax.scatter([0], [0], marker='+', s=260, linewidth=2.5, color='black',
               label=f'Image center ({cx}, {cy})', zorder=5)
    ax.errorbar(*mean, xerr=std[0], yerr=std[1], fmt='X', color='#bd2634',
                markersize=13, capsize=6, elinewidth=1.5,
                label='All-sample mean; bars = sample SD (not mean uncertainty)', zorder=6)
    ax.scatter(*median, s=150, marker='D', facecolors='none', edgecolors='#373737',
               linewidths=1.5, label='Coordinate-wise median', zorder=5)
    ax.set(xlim=(-30, 200), ylim=(205, -30),
           xlabel='Delta x (pixels; right is positive)',
           ylabel='Delta y (pixels; down is positive)',
           title=f'Pixel observation group | n={len(values)} | {width} x {height}\n'
                 f'Mean: ({mean[0]:.2f}, {mean[1]:.2f}) px   '
                 f'Median: ({median[0]:.1f}, {median[1]:.1f}) px')
    ax.set_aspect('equal', adjustable='box')
    ax.grid(alpha=0.2)
    ax.legend(loc='upper left', fontsize=8.5)
    fig.savefig(args.output_dir / 'sample_group.png', dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

"""
Ray Diagram Generator — matplotlib-based image generation for Physics diagrams.

Takes generation_description from content generation output and produces clean
educational ray diagrams.

For production: this handles the MATPLOTLIB path. Gemini image gen is a separate module.
"""

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import os
import sys
import json


def draw_plane_mirror_reflection(ax, angle_with_surface=25):
    """Draw plane mirror reflection with incident/reflected rays and angles."""
    # Mirror (horizontal line with shading)
    ax.plot([-2, 2], [0, 0], 'k-', linewidth=2)
    # Shading below mirror
    for x in np.arange(-2, 2, 0.15):
        ax.plot([x, x - 0.15], [0, -0.2], 'k-', linewidth=0.5, alpha=0.5)

    # Angles
    angle_incidence = 90 - angle_with_surface  # angle with normal
    theta_i = np.radians(angle_incidence)

    # Point of incidence
    px, py = 0, 0

    # Normal (dashed, perpendicular to mirror)
    ax.plot([0, 0], [-1.2, 1.8], 'k--', linewidth=1, alpha=0.7)
    ax.text(0.1, 1.6, 'Normal', fontsize=8, style='italic')

    # Incident ray
    ray_len = 2.0
    ix = -ray_len * np.sin(theta_i)
    iy = ray_len * np.cos(theta_i)
    ax.annotate('', xy=(px, py), xytext=(ix, iy),
                arrowprops=dict(arrowstyle='->', color='blue', lw=1.5))
    ax.text(ix - 0.3, iy * 0.6, 'Incident\nray', fontsize=8, color='blue', ha='right')

    # Reflected ray
    rx = ray_len * np.sin(theta_i)
    ry = ray_len * np.cos(theta_i)
    ax.annotate('', xy=(rx, ry), xytext=(px, py),
                arrowprops=dict(arrowstyle='->', color='red', lw=1.5))
    ax.text(rx + 0.1, ry * 0.6, 'Reflected\nray', fontsize=8, color='red')

    # Angle arcs
    arc_r = 0.6
    # Angle of incidence
    arc_i = patches.Arc((0, 0), arc_r * 2, arc_r * 2, angle=0,
                         theta1=90 - angle_incidence, theta2=90, color='blue', lw=1.5)
    ax.add_patch(arc_i)
    ax.text(-0.15, 0.45, f'{angle_incidence}°', fontsize=9, color='blue', ha='center')

    # Angle of reflection
    arc_r2 = patches.Arc((0, 0), arc_r * 2, arc_r * 2, angle=0,
                          theta1=90, theta2=90 + angle_incidence, color='red', lw=1.5)
    ax.add_patch(arc_r2)
    ax.text(0.15, 0.45, f'{angle_incidence}°', fontsize=9, color='red', ha='center')

    ax.text(2.1, -0.3, 'Mirror', fontsize=9)
    ax.set_xlim(-2.5, 2.8)
    ax.set_ylim(-1.5, 2.2)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('Reflection at a Plane Mirror', fontsize=11, fontweight='bold', pad=10)


def draw_sign_convention(ax):
    """Draw New Cartesian Sign Convention for spherical mirrors."""
    # Axes
    ax.annotate('', xy=(3.5, 0), xytext=(-3.5, 0),
                arrowprops=dict(arrowstyle='->', lw=1.5, color='black'))
    ax.annotate('', xy=(0, 2.5), xytext=(0, -2.5),
                arrowprops=dict(arrowstyle='->', lw=1.5, color='black'))

    # Concave mirror arc
    theta = np.linspace(-0.6, 0.6, 50)
    R = 4
    mx = R - R * np.cos(theta)
    my = R * np.sin(theta)
    ax.plot(mx, my, 'k-', linewidth=2.5)
    # Shading
    for t in np.linspace(-0.5, 0.5, 8):
        x1 = R - R * np.cos(t)
        y1 = R * np.sin(t)
        ax.plot([x1, x1 + 0.15], [y1, y1], 'k-', linewidth=0.5, alpha=0.5)

    # Labels
    ax.text(0, -0.25, 'P', fontsize=10, fontweight='bold', ha='center')
    ax.text(3.2, -0.3, '+x', fontsize=9, color='green')
    ax.text(-3.2, -0.3, '-x', fontsize=9, color='red')
    ax.text(0.15, 2.2, '+y', fontsize=9, color='green')
    ax.text(0.15, -2.2, '-y', fontsize=9, color='red')

    # Direction arrow
    ax.annotate('', xy=(1.5, 1.8), xytext=(-1.5, 1.8),
                arrowprops=dict(arrowstyle='->', lw=1, color='gray'))
    ax.text(0, 1.95, 'Direction of incident light', fontsize=7, ha='center', color='gray')

    # Region labels
    ax.text(-2, 0.8, 'Object side\n(distances -ve)', fontsize=8, ha='center', color='red',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#ffe0e0', alpha=0.5))
    ax.text(2, 0.8, 'Behind mirror\n(distances +ve)', fontsize=8, ha='center', color='green',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#e0ffe0', alpha=0.5))

    ax.set_xlim(-4, 4)
    ax.set_ylim(-3, 2.5)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('New Cartesian Sign Convention', fontsize=11, fontweight='bold', pad=10)


def draw_convex_lens_ray_diagram(ax, object_position='at_2F'):
    """Draw convex lens ray diagram for different object positions."""
    # Lens (vertical double-arrow shape)
    lens_x = 0
    lens_h = 2.0
    ax.plot([lens_x, lens_x], [-lens_h, lens_h], 'b-', linewidth=2)
    # Lens tips
    ax.plot([lens_x - 0.15, lens_x, lens_x + 0.15], [lens_h - 0.15, lens_h, lens_h - 0.15], 'b-', lw=1.5)
    ax.plot([lens_x - 0.15, lens_x, lens_x + 0.15], [-lens_h + 0.15, -lens_h, -lens_h + 0.15], 'b-', lw=1.5)

    # Principal axis
    ax.plot([-5, 5], [0, 0], 'k-', linewidth=0.5, alpha=0.5)

    f = 2  # focal length

    # Mark focal points and 2F points
    for label, pos in [('F₁', -f), ('F₂', f), ('2F₁', -2 * f), ('2F₂', 2 * f), ('O', 0)]:
        ax.plot(pos, 0, 'ko', markersize=3)
        ax.text(pos, -0.35, label, fontsize=8, ha='center')

    if object_position == 'at_2F':
        obj_x = -2 * f
        obj_h = 1.2
        # Object arrow
        ax.annotate('', xy=(obj_x, obj_h), xytext=(obj_x, 0),
                    arrowprops=dict(arrowstyle='->', color='green', lw=2))
        ax.text(obj_x - 0.3, obj_h / 2, 'Object', fontsize=8, color='green', rotation=90, va='center')

        # Ray 1: parallel to axis → through F2
        ax.annotate('', xy=(0, obj_h), xytext=(obj_x, obj_h),
                    arrowprops=dict(arrowstyle='-', color='orange', lw=1.5))
        ax.annotate('', xy=(2 * f, 0), xytext=(0, obj_h),
                    arrowprops=dict(arrowstyle='->', color='orange', lw=1.5))

        # Ray 2: through O → straight
        ax.annotate('', xy=(2 * f, -obj_h), xytext=(obj_x, obj_h),
                    arrowprops=dict(arrowstyle='->', color='purple', lw=1.5))

        # Image arrow (inverted, same size at 2F2)
        ax.annotate('', xy=(2 * f, -obj_h), xytext=(2 * f, 0),
                    arrowprops=dict(arrowstyle='->', color='red', lw=2))
        ax.text(2 * f + 0.3, -obj_h / 2, 'Image', fontsize=8, color='red', rotation=90, va='center')

        ax.set_title('Convex Lens: Object at 2F₁ → Image at 2F₂ (same size, inverted)', fontsize=10, fontweight='bold')

    elif object_position == 'between_F_and_O':
        obj_x = -f * 0.6
        obj_h = 0.8

        # Object arrow
        ax.annotate('', xy=(obj_x, obj_h), xytext=(obj_x, 0),
                    arrowprops=dict(arrowstyle='->', color='green', lw=2))

        # Ray 1: parallel to axis → through F2
        ax.annotate('', xy=(0, obj_h), xytext=(obj_x, obj_h),
                    arrowprops=dict(arrowstyle='-', color='orange', lw=1.5))
        ax.plot([0, 4], [obj_h, obj_h - (obj_h / f) * 4], 'orange', lw=1.5)

        # Ray 2: through O → straight
        slope = obj_h / obj_x
        ax.plot([obj_x, 4], [obj_h, obj_h + slope * (4 - obj_x)], 'purple', lw=1.5)

        # Virtual image (dashed extensions backward)
        img_x = -3.5
        img_h = 2.0
        ax.annotate('', xy=(img_x, img_h), xytext=(img_x, 0),
                    arrowprops=dict(arrowstyle='->', color='red', lw=2, linestyle='dashed'))
        ax.plot([0, img_x], [obj_h, img_h], 'orange', lw=1, linestyle='--', alpha=0.6)

        ax.text(obj_x - 0.3, obj_h / 2, 'Object', fontsize=8, color='green', rotation=90, va='center')
        ax.text(img_x - 0.3, img_h / 2, 'Virtual\nImage', fontsize=7, color='red', ha='right')

        ax.set_title('Convex Lens: Object between F₁ and O → Virtual, erect, enlarged', fontsize=10, fontweight='bold')

    ax.set_xlim(-5.5, 5.5)
    ax.set_ylim(-2.8, 2.8)
    ax.set_aspect('equal')
    ax.axis('off')


def draw_concave_lens_ray(ax, ray_type='towards_focus'):
    """Draw single ray through concave lens."""
    lens_x = 0
    lens_h = 2.0
    f = 2

    # Lens (diverging shape)
    ax.plot([lens_x, lens_x], [-lens_h, lens_h], 'b-', linewidth=2)
    ax.plot([lens_x + 0.15, lens_x, lens_x - 0.15], [lens_h - 0.15, lens_h, lens_h - 0.15], 'b-', lw=1.5)
    ax.plot([lens_x + 0.15, lens_x, lens_x - 0.15], [-lens_h + 0.15, -lens_h, -lens_h + 0.15], 'b-', lw=1.5)

    # Principal axis
    ax.plot([-4, 4], [0, 0], 'k-', linewidth=0.5, alpha=0.5)

    # Mark points
    for label, pos in [('F₁', -f), ('F₂', f), ('O', 0)]:
        ax.plot(pos, 0, 'ko', markersize=3)
        ax.text(pos, -0.3, label, fontsize=8, ha='center')

    if ray_type == 'towards_focus':
        # Ray directed towards F2 on opposite side → emerges parallel
        ray_h = 1.0
        ax.annotate('', xy=(0, ray_h), xytext=(-4, ray_h + (ray_h / (4 + f)) * 4),
                    arrowprops=dict(arrowstyle='->', color='orange', lw=1.5))
        ax.annotate('', xy=(4, ray_h), xytext=(0, ray_h),
                    arrowprops=dict(arrowstyle='->', color='orange', lw=1.5))

        # Dashed extension to F2
        ax.plot([0, f], [ray_h, 0], 'orange', lw=1, linestyle='--', alpha=0.5)

        ax.set_title('Concave Lens: Ray towards F₂ → emerges parallel', fontsize=10, fontweight='bold')

    elif ray_type == 'through_F1':
        # Ray through F1 → after refraction appears to come from F2
        ray_h = 1.0
        ax.annotate('', xy=(0, ray_h), xytext=(-4, 0.2),
                    arrowprops=dict(arrowstyle='->', color='purple', lw=1.5))
        # Emerges parallel
        ax.annotate('', xy=(4, ray_h), xytext=(0, ray_h),
                    arrowprops=dict(arrowstyle='->', color='purple', lw=1.5))

        ax.set_title('Convex Lens: Ray through F₁ → emerges parallel', fontsize=10, fontweight='bold')

    ax.set_xlim(-4.5, 4.5)
    ax.set_ylim(-2.5, 2.8)
    ax.set_aspect('equal')
    ax.axis('off')


def generate_all_flagged(flags, output_dir):
    """Generate all flagged images."""
    os.makedirs(output_dir, exist_ok=True)

    for i, flag in enumerate(flags):
        fig, ax = plt.subplots(1, 1, figsize=(10, 7), dpi=150)

        desc = flag.get('generation_description', '').lower()
        sid = flag['subconcept_id']
        location = flag['location']

        if 'plane mirror' in desc:
            angle = 25  # extract from description if present
            draw_plane_mirror_reflection(ax, angle_with_surface=angle)
        elif 'sign convention' in desc or 'cartesian' in desc:
            draw_sign_convention(ax)
        elif 'convex lens' in desc and 'at 2f' in desc:
            draw_convex_lens_ray_diagram(ax, object_position='at_2F')
        elif 'convex lens' in desc and ('between f' in desc or 'magnifying' in desc):
            draw_convex_lens_ray_diagram(ax, object_position='between_F_and_O')
        elif 'concave lens' in desc:
            draw_concave_lens_ray(ax, ray_type='towards_focus')
        elif 'convex lens' in desc and 'through' in desc and 'focus' in desc:
            draw_concave_lens_ray(ax, ray_type='through_F1')
        else:
            ax.text(0.5, 0.5, f'Unhandled: {desc[:80]}', transform=ax.transAxes, ha='center')

        plt.tight_layout()
        fname = f'{sid}_{location}.png'
        fpath = os.path.join(output_dir, fname)
        plt.savefig(fpath, bbox_inches='tight', facecolor='white', edgecolor='none')
        plt.close()

        size_kb = os.path.getsize(fpath) // 1024
        from PIL import Image
        img = Image.open(fpath)
        w, h = img.size
        print(f"  Generated: {fname} ({w}x{h}px, {size_kb}KB)")


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    # Load flags from full results
    base = os.path.join(os.path.dirname(__file__), '..', '..')
    out_dir = os.path.join(base, 'experiments/05_content_generation/ch09_full')

    flags = []
    for fname in sorted(os.listdir(out_dir)):
        if not fname.endswith('.json') or fname == 'ch09_full_results.json':
            continue
        with open(os.path.join(out_dir, fname), 'r') as f:
            data = json.load(f)
        content = data.get('content', {})
        if 'error' in content:
            continue
        sid = content.get('subconcept_id', fname.replace('.json', ''))

        # Theory
        tvc = content.get('theory_visual_content', {})
        if tvc.get('image_generation_needed'):
            flags.append({
                'subconcept_id': sid, 'location': 'theory',
                'generation_description': tvc.get('generation_description', ''),
            })

        # Content items
        for item_type in ['scqs', 'subjective', 'examples']:
            for j, item in enumerate(content.get(item_type, [])):
                vc = item.get('visual_content', {})
                if vc.get('image_generation_needed'):
                    flags.append({
                        'subconcept_id': sid, 'location': f'{item_type}_{j + 1}',
                        'generation_description': vc.get('generation_description', ''),
                    })

    print(f"Found {len(flags)} image generation flags\n")

    img_out = os.path.join(base, 'experiments/05_content_generation/ch09_generated_images')
    generate_all_flagged(flags, img_out)

    print(f"\nAll images saved to: {img_out}")

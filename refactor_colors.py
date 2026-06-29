import os
import re

color_map = {
    "#00685f": "primary",
    "#005a54": "primary-hover",
    "#005a52": "primary-hover",
    "#008378": "primary-light",
    "#e0f2f1": "primary-50",
    "#b2dfdb": "primary-200",
    "#00c4b4": "secondary",
    "#0d9488": "secondary-dark",
    "#0b7a6d": "secondary-dark-hover",
    "#0b7a70": "secondary-dark-hover",
    "#ba1a1a": "danger",
    "#00855b": "success",
    "#006947": "success-dark",
    "#f4fffc": "success-light",
    "#2170e4": "info",
    "#0058be": "info-dark",
    "#2563eb": "info-light",
    "#191c1d": "text-main",
    "#3d4947": "text-muted",
    "#6b7280": "text-light",
    "#6d7a77": "text-alt",
    "#f8f9fa": "bg-main",
    "#ffffff": "bg-surface",
    "#f3f4f5": "bg-alt",
    "#e1e3e4": "bg-muted",
    "#e7e8e9": "bg-muted-alt",
    "#edeeef": "bg-hover",
    "#bcc9c6": "border-main",
    "#d1d5db": "border-dark",
    # 8-character hex codes mapped to semantic names with opacity
    "#00685f0d": "primary/5",
    "#00685f33": "primary/20",
    "#0058be0d": "info-dark/5",
    "#00855b33": "success/20",
    "#00855b0d": "success/5",
    "#f8f9facc": "bg-main/80",
    "#00685f0a": "primary/5",
    "#00685f1a": "primary/10"
}

def refactor_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = content
    
    def replacer(match):
        prefix = match.group(1) # e.g. bg, text, border, shadow, hover:bg
        hex_code = "#" + match.group(2).lower()
        opacity = match.group(3)
        
        if hex_code in color_map:
            semantic_name = color_map[hex_code]
            replacement = f"{prefix}-{semantic_name}"
            if opacity:
                replacement += f"/{opacity}"
            return replacement
        
        return match.group(0)

    # regex to match arbitrary color classes
    pattern = re.compile(r'([a-zA-Z0-9:-]+)-\[#([0-9a-fA-F]{3,8})\](?:/([0-9]+))?')
    new_content = pattern.sub(replacer, new_content)

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

def main():
    src_dir = "c:/Users/JOY/Documents/Code/EccomercePlatformProject/v1/src"
    count = 0
    for root, dirs, files in os.walk(src_dir):
        for file in files:
            if file.endswith('.html') or file.endswith('.py'):
                refactor_file(os.path.join(root, file))
                count += 1
    print(f"Scanned {count} files.")

if __name__ == '__main__':
    main()

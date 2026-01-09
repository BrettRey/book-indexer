import glob
import re
import os

# Regex to find our tags: \isi{term}, \ini{term}, \ili{term}
# Also standard \index{...} if any remain
TAG_PATTERN = re.compile(r"\\(isi|ini|ili|index|sindex|nindex|lindex)\{([^}]+)")

def generate_report(dir_path):
    files = sorted(glob.glob(os.path.join(dir_path, "*.tex")))
    
    print("--- INDEX REPORT ---")
    
    total_tags = 0
    all_terms = set()
    
    for file_path in files:
        filename = os.path.basename(file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        tags = TAG_PATTERN.findall(content)
        if tags:
            print(f"\nFile: {filename} ({len(tags)} tags)")
            # Group by type
            by_type = {'subject': [], 'name': [], 'language': [], 'other': []}
            
            for cmd, term in tags:
                total_tags += 1
                all_terms.add(term)
                
                # Clean term for display
                display = term
                
                if 'n' in cmd:
                    by_type['name'].append(display)
                elif 'l' in cmd and 'lindex' in cmd or 'ili' in cmd:
                    by_type['language'].append(display)
                elif 's' in cmd or 'isi' in cmd:
                    by_type['subject'].append(display)
                else:
                    by_type['other'].append(display)
            
            for type_, terms in by_type.items():
                if terms:
                    # Show first few terms
                    unique_terms = sorted(list(set(terms)))
                    limit = 5
                    shown = ", ".join(unique_terms[:limit])
                    remainder = len(unique_terms) - limit
                    suffix = f"... (+{remainder} more)" if remainder > 0 else ""
                    print(f"  {type_.capitalize()}: {shown} {suffix}")

    print(f"\nTotal Tags Found: {total_tags}")
    print(f"Unique Terms: {len(all_terms)}")

if __name__ == "__main__":
    generate_report(".gemini/tmp/langsci-81/chapters")

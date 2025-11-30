import fitz  
import re
import pandas as pd


# Modify PDF location and name as necessary
pdf_loc = 'papers/'
pdf_name = 'ACL_paper.pdf'


def extract_acl_references(pdf_path, footer_margin=50, header_margin=50, debug=False):
    """
    Extract references from an ACL format research paper PDF.
    Uses line-level bbox x-coordinates to detect indentation.
    
    Args:
        pdf_path: Path to the PDF file
        footer_margin: Height of footer area to ignore (default 50)
        header_margin: Height of header area to ignore (default 50)
        debug: If True, print diagnostic information
        
    Returns:
        List of reference strings in order
    """
    references = []
    doc = fitz.open(pdf_path)
    
    # Find References section
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    
    ref_pattern = r'\n\s*(References|REFERENCES|Bibliography)\s*\n'
    match = re.search(ref_pattern, full_text)
    
    if not match:
        print("Could not find References section")
        doc.close()
        return references
    
    ref_start_char = match.end()
    current_char = 0
    ref_start_page = 0
    
    for page_num in range(len(doc)):
        page_text = doc[page_num].get_text()
        if current_char + len(page_text) >= ref_start_char:
            ref_start_page = page_num
            break
        current_char += len(page_text)
    
    # Extract lines with their bboxes
    all_lines = []  # Store (page_num, column, y_pos, x_pos, text)
    
    for page_num in range(ref_start_page, len(doc)):
        page = doc[page_num]
        width = page.rect.width
        height = page.rect.height
        mid_x = width / 2
        
        clip = +page.rect
        clip.y1 -= footer_margin
        clip.y0 += header_margin
        
        blocks = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT, clip=clip)["blocks"]
        
        for block in blocks:
            if block["type"] == 0:  
                block_bbox = block["bbox"]
                block_center_x = (block_bbox[0] + block_bbox[2]) / 2
                column = 0 if block_center_x < mid_x else 1
                
                for line in block["lines"]:
                    line_bbox = line["bbox"]
                    line_text = ""
                    for span in line["spans"]:
                        line_text += span["text"]
                    
                    if line_text.strip():
                        all_lines.append((page_num, column, line_bbox[1], line_bbox[0], line_text.strip()))
    
    # Sort lines: by page, then column, then y-position
    all_lines.sort(key=lambda x: (x[0], x[1], x[2]))
    
    if not all_lines:
        doc.close()
        return references
    
    from collections import defaultdict
    column_min_x = defaultdict(list)
    
    for page_num, column, y_pos, x_pos, text in all_lines:
        key = (page_num, column)
        column_min_x[key].append(x_pos)
        old_text = ''
    
    # Calculate minimum x for each (page, column)
    min_x_map = {}
    for key, x_positions in column_min_x.items():
        min_x_map[key] = min(x_positions)
    
    if debug:
        print("Min x-positions per (page, column):")
        for key, min_x in sorted(min_x_map.items()):
            print(f"  Page {key[0]}, Col {key[1]}: {min_x:.2f}")
    
    # Parse references using indentation
    tolerance = 3  # pixels - stricter tolerance
    current_ref = ""
    in_references = False
    prev_was_A = False
    ref_count = 0
    
    if debug:
        print(f"\nProcessing lines (showing first 50):")
    
    page_list = []

    for i, (page_num, column, y_pos, x_pos, text) in enumerate(all_lines):
        if not in_references:
            if re.search(r'(References|REFERENCES|Bibliography)', text):
                in_references = True
                if debug:
                    print(f"Found References at line {i}")
                continue
        
        if not in_references:
            continue

        # Check for appendix
        if text.strip() == "A":
            prev_was_A = True
            if debug:
                print(f"Found 'A' at line {i}, checking next line...")
            continue
        
        if prev_was_A:
            if debug:
                print(f"Appendix starts at line {i}: '{text}', stopping")
            break
        
        if re.match(r'^\n*(?:A\s+[A-Z])', text):
            if page_num in page_list:
                continue
            if debug:
                print(f"Found Appendix at line {i}, stopping")
            break
        
        page_list.append(page_num)

        # Determine if this is a new reference based on indentation
        key = (page_num, column)
        min_x = min_x_map.get(key, x_pos)
        x_diff = x_pos - min_x
        if column == 0:
            tolerance = 3
        elif column == 1:
            tolerance = 15
        is_new_ref = abs(x_diff) <= tolerance
        
        if debug and in_references and text.isnumeric():
            print(f"  [{i}] P{page_num}C{column} x={x_pos:.1f} min={min_x:.1f} diff={x_diff:.1f} {'NEW' if is_new_ref else 'CONT'}: {text[:60]}")
        
        new_text = text
        if is_new_ref:
            # Save previous reference
            if text.isnumeric():
                continue
            if current_ref:
                references.append(current_ref.strip())
                ref_count += 1
            # Start new reference
            current_ref = new_text.strip('-')
        else:
            # Continuation line
            if current_ref:
                if old_text[-1] == '-':
                    current_ref += new_text.strip('-')
                else:
                    current_ref += " " + new_text.strip('-')
            else:
                current_ref = new_text.strip('-')
        
        prev_was_A = False
        old_text = text
    
    if current_ref:
        references.append(current_ref.strip())
        ref_count += 1
    
    if debug:
        print(f"\nTotal references found: {ref_count}")
    
    doc.close()
    return references


def references_dict(references):
    """ 
    Store each reference in a dataframe

    Args:   
        List of reference strings in order
    Returns: 
        Dataframe of authors, year, title, venue 
        and DOI from each reference
    """
    count = 0
    ref_dict = {}

    for i, ref in enumerate(references):
        ref_dict[i]={}
        count += 1
        pattern_1 = '(^.+?)\.\s((?:19|20)\d{2})\.\s(.*)'
        obj = re.search(pattern_1, ref)
        ref_dict[i]['authors'] = obj.group(1)       # Saves string of authors
        ref_dict[i]['year'] = obj.group(2)          # Saves year
        other = obj.group(3)

        pattern_2 = r'^(.*?\.)(\s+.*)?$'
        obj_2 = re.search(pattern_2, other)
        ref_dict[i]['title'] = obj_2.group(1).strip('.')    # Saves title

        if obj_2.group(2):
            venue_det = obj_2.group(2).strip()
            pattern_3 = re.compile('(?:In\s+)?(?:Proceedings\s+of\s+)?'
                                   '(?:the\s+)?(.+?)(?:,\s+(?=[A-Z][a-z]+,\s+'
                                   '[A-Z]|Virtual|Online|pages)|,\s(abs/.+)?\.|\.$)')
            obj_3 = re.search(pattern_3,venue_det)
            # Saves venue and DOI
            if obj_3.group(1):
                ref_dict[i]['venue'] = obj_3.group(1)
            else:
                ref_dict[i]['venue'] = ''
            if obj_3.group(2):
                ref_dict[i]['doi'] = obj_3.group(2)
            else:
                ref_dict[i]['doi'] = ''
        else:
            ref_dict[i]['venue'] = ''
            ref_dict[i]['doi'] = ''

        # print('-----')
        if count == 20:
            break
    
    df = pd.DataFrame.from_dict(ref_dict,orient='index')
    return df


def main():
    # Extract references
    refs = extract_acl_references(
        pdf_loc+pdf_name,
        debug=False
        )
    ref_df = references_dict(refs)

    # Write dataframe to txt file
    ref_df.to_csv(f"{pdf_loc+pdf_name.strip('.pdf')}.txt", sep='\t', index=True)

if __name__=="__main__":
    main()
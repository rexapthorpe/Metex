"""Parse the exact address format produced by the bid form; never invent fields."""
import re


def bid_shipping(bid):
    address=bid['delivery_address'] or ''
    parts=[p.strip() for p in re.split(r'•|\n',address) if p.strip()]
    if len(parts) not in (2,3):
        raise ValueError('Complete bid delivery address is required')
    match=re.fullmatch(r'(.+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)',parts[-1])
    if not match: raise ValueError('Bid address requires city, state and postal code')
    result={'shipping_address':address,'line1':parts[0],'city':match[1].strip(),
      'state':match[2],'postal_code':match[3],'country':'US',
      'recipient_first':bid['recipient_first_name'],'recipient_last':bid['recipient_last_name']}
    if len(parts)==3: result['line2']=parts[1]
    return result

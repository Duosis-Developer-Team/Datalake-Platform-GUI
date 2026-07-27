"""Colocation per-rack-U unit price.

Two sources, resolved in the service layer:
  - gui_crm_price_override (webui-db) — operator-set price, wins when present.
  - discovery_crm_productpricelevels (bulutlake) — the CRM list price.

Verified 2026-07-27: productid ee635018-... ("Veri Merkezi Barindirma Hizmeti
(U)") is the ONLY CRM product priced with uomid_name = 'U'. Its TL row sits on
the "TL Fiyat Listesi" price list with statecode = 0, so the active-price-list
filter keeps it.
"""

# bulutlake — CRM list price for the per-U colocation product, TL only.
# Newest row first: CRM keeps history and we want the current price.
COLOCATION_CRM_UNIT_PRICE = """
SELECT ppl.amount::double precision
FROM   discovery_crm_productpricelevels ppl
JOIN   discovery_crm_pricelevels pl ON pl.pricelevelid = ppl.pricelevelid
WHERE  ppl.productid = %s
  AND  pl.statecode = 0
  AND  ppl.transactioncurrency_text = 'Turkish Lira'
ORDER  BY ppl.modifiedon DESC NULLS LAST
LIMIT  1;
"""

# webui-db — operator override for the same product.
COLOCATION_PRICE_OVERRIDE = """
SELECT unit_price_tl
FROM   gui_crm_price_override
WHERE  productid = %s
LIMIT  1;
"""

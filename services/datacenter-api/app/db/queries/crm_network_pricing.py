"""CRM price lookup for network backbone billing (datacenter-api)."""

from __future__ import annotations

NETWORK_DC_ACCESS_PRODUCT_ID = "e2f585bb-c2e0-f011-8406-6045bd9c244d"
NETWORK_DC_ACCESS_PANEL_KEY = "network_dc_access"
NETWORK_DC_ACCESS_RESOURCE_UNIT = "Mbit"
NETWORK_DC_ACCESS_PRODUCT_NAME = "Veri Merkezi Erişim ve L3 DDoS Hizmeti"

# Price override first, then catalog TL price (mirrors customer-api sellable queries).
GET_PRICE_OVERRIDE_FOR_PANEL = """
SELECT po.unit_price_tl, po.currency, po.productid
FROM   gui_crm_price_override   po
JOIN   gui_crm_service_pages    sp  ON sp.panel_key = %s
JOIN   gui_crm_service_mapping_seed     sm  ON sm.page_key = sp.page_key
LEFT  JOIN gui_crm_service_mapping_override ov ON ov.productid = sm.productid
WHERE  po.productid = COALESCE(ov.productid, sm.productid)
ORDER BY (po.unit_price_tl IS NOT NULL) DESC, po.updated_at DESC
LIMIT 1;
"""

CATALOG_TL_PRICE_FOR_PRODUCT = """
SELECT ppl.amount, pl.transactioncurrency_text
FROM   discovery_crm_productpricelevels ppl
JOIN   discovery_crm_pricelevels        pl  ON pl.pricelevelid = ppl.pricelevelid
WHERE  ppl.productid = %s
ORDER BY (pl.transactioncurrency_text = 'TL') DESC,
         ppl.amount DESC
LIMIT 1;
"""

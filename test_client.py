#!/usr/bin/env python3
"""Quick test for NESCO client - no Telegram token needed."""
from nesco_client import NescoClient


def test():
    """Test the NESCO client."""
    print("🔍 Testing NESCO client...")
    print("-" * 40)
    
    with NescoClient() as client:
        # Test balance/customer info
        print("\n📋 Testing Customer Info...")
        info = client.get_customer_info("77900157")
        
        if info:
            print("✅ Successfully fetched customer data!\n")
            print(f"👤 Customer Name: {info.customer_name}")
            print(f"💰 Balance: ৳{info.balance:.2f}")
            print(f"🕐 Updated: {info.balance_updated_at}")
            print(f"⚠️ Min Recharge: ৳{info.min_recharge:.2f}")
            print("\n" + "-" * 40)
            print("\nFull formatted output:")
            print(info.format_telegram())
        else:
            print("❌ Failed to parse customer data")
        
        print("\n" + "=" * 40)
        
        # Test monthly usage
        print("\n📊 Testing Monthly Usage...")
        usage = client.get_monthly_usage("77900157")
        
        if usage:
            print("✅ Successfully fetched monthly usage!\n")
            print(usage.format_telegram())
        else:
            print("❌ Failed to parse monthly usage data")


def debug_html():
    """Save raw HTML for debugging."""
    import httpx
    from parser import NescoHTMLParser
    
    parser = NescoHTMLParser()
    
    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        # Get CSRF token
        resp = client.get("https://customer.nesco.gov.bd/pre/panel")
        token = parser.extract_csrf_token(resp.text)
        
        # Fetch customer data
        resp = client.post(
            "https://customer.nesco.gov.bd/pre/panel",
            data={
                "_token": token,
                "cust_no": "77900157",
                "submit": "রিচার্জ হিস্ট্রি",
            }
        )
        
        # Save HTML for inspection
        with open("debug_response.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print("✅ Saved HTML to debug_response.html")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        debug_html()
    else:
        test()

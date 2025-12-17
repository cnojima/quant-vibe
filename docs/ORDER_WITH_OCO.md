# Sample Order with OCO (One Cancels Other)

Orders should be placed with
 - target profit
 - stop loss to protect against drawdowns

Schwab's API enables submitting an order with child orders:

### Conditional Order: One Triggers A One Cancels Another
> Buy 5 shares of XYZ at a Limit price of $14.97 good for the Day. Once filled, 2 sell orders are immediately sent: Sell 5 shares of XYZ at a Limit price of $15.27 and Sell 5 shares of XYZ with a Stop order where the stop price is $11.27. If one of the sell orders fill, the other order is immediately cancelled. Both Sell orders are Good till Cancel. Also known as a 1st Trigger OCO order.

The below order shows:
1. LIMIT buy of 5 shares `XYZ`at 14.97 a share.
2. OCO Child Order (placed if parent is filled)
3. GTC LIMIT sell at 15.27 (profit target)
4. GTC LIMIT sell at 11.27 (stop loss)

```json
{ 
  "orderStrategyType": "TRIGGER", 
  "session": "NORMAL", 
  "duration": "DAY", 
  "orderType": "LIMIT", 
  "price": 14.97, 
  "orderLegCollection": [ 
   { 
    "instruction": "BUY", 
    "quantity": 5, 
    "instrument": { 
     "assetType": "EQUITY", 
     "symbol": "XYZ" 
    } 
   } 
  ], 
  "childOrderStrategies": [ 
   { 
    "orderStrategyType": "OCO", 
    "childOrderStrategies": [ 
     { 
      "orderStrategyType": "SINGLE", 
      "session": "NORMAL", 
      "duration": "GOOD_TILL_CANCEL", 
      "orderType": "LIMIT", 
      "price": 15.27, 
      "orderLegCollection": [ 
       { 
        "instruction": "SELL", 
        "quantity": 5, 
        "instrument": { 
         "assetType": "EQUITY", 
         "symbol": "XYZ" 
        } 
       } 
      ] 
     }, 
     { 
      "orderStrategyType": "SINGLE", 
      "session": "NORMAL", 
      "duration": "GOOD_TILL_CANCEL", 
      "orderType": "STOP", 
      "stopPrice": 11.27, 
      "orderLegCollection": [ 
       { 
        "instruction": "SELL", 
        "quantity": 5, 
        "instrument": { 
         "assetType": "EQUITY", 
         "symbol": "XYZ" 
        } 
       } 
      ] 
     } 
    ] 
   } 
  ] 
}
```
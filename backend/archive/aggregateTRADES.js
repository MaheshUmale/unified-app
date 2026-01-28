db.trade_signals.aggregate([
  // Step 1: Filter to start with only ENTRY documents
  {
    $match: {
      type: "ENTRY"
    }
  },
  // Step 2: Perform the join (lookup the corresponding EXIT document)
  {
    $lookup: {
      from: "trade_signals",    // The same collection you are joining from
      localField: "trade_id",        // Field from the input documents (ENTRY's trade_id)
      foreignField: "trade_id",      // Field from the 'from' documents (EXIT's trade_id)
      as: "exitDetails",             // Name of the new array field containing the joined document(s)
      // Step 3 (Optional): Further filtering within the lookup
      pipeline: [
        {
          $match: {
            type: "EXIT"
          }
        }
      ]
    }
  },
  // Step 4: Convert the 'exitDetails' array into a single object
  // (Since there should only be one match)
  {
    $unwind: "$exitDetails"
  },
  // Step 5 (Optional): Project and reshape the final document to make analysis easier
  {
    $project: {
      _id: 0, // Exclude mongo's internal IDs if you want cleaner output
      trade_id: "$trade_id",
      strategy: "$strategy",
      instrumentKey: "$instrumentKey",
      entry: {
          time: "$timestamp",
          price: "$ltp",
          position: "$position_after",
          reason: "$reason"
      },
      exit: {
          time: "$exitDetails.timestamp",
          price: "$exitDetails.exit_price",
          reason_code: "$exitDetails.reason_code"
      },
      pnl: "$exitDetails.pnl",
      sl_price: "$sl_price",
      tp_price: "$tp_price",
      duration_seconds: { $subtract: ["$exitDetails.timestamp", "$timestamp"] }
    }
  }
])

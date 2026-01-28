// MongoDB Playground
// Use Ctrl+Space inside a snippet or a string literal to trigger completions.

// The current database to use.
use("upstox_strategy_db");

// Define the cutoff date (e.g., everything before November 1st, 2025)
const cutoffDate = ISODate("2025-12-11T00:00:00Z");

// Define collections
const sourceCollection = db.tick_data;
const destCollection = db.tick_data_bkp;

// Find all documents older than the cutoff date
const oldDataCursor = sourceCollection.find({ "inserttime": { $lt: cutoffDate } });

// Convert the cursor to an array and insert them into the backup collection
// Note: This operation can take a while if you have millions of records.
// It is best done in maintenance window or in smaller batches.
while (await oldDataCursor.hasNext()) {
    const batch = [];
    for (let i = 0; i < 1000 && await oldDataCursor.hasNext(); i++) {
        batch.push(await oldDataCursor.next());
    }
    if (batch.length > 0) {
        await destCollection.insertMany(batch);
        print(`Inserted ${batch.length} documents into tick_data_bkp...`);
    }
}
print("Insertion to backup complete.");

await destCollection.createIndex({ "inserttime": -1 });
await destCollection.createIndex({ "tickerSymbol": 1, "inserttime": -1 });
print("Indexes created for tick_data_bkp.");

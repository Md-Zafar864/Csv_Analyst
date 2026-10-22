from app.database import SavedQuery, engine

# Delete the old saved_queries table
SavedQuery.__table__.drop(bind=engine, checkfirst=True)

# Create the table again with all defined columns
SavedQuery.__table__.create(bind=engine)

print("saved_queries table recreated successfully!")
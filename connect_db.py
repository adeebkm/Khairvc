#!/usr/bin/env python3
"""
Interactive PostgreSQL Database Connection Script
Allows you to query and interact with the database directly
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from tabulate import tabulate

# Load environment variables
load_dotenv()

def get_database_url():
    """Get database URL from environment or prompt user"""
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("⚠️  DATABASE_URL not found in environment variables.")
        print("Please provide your PostgreSQL connection string:")
        print("Format: postgresql://user:password@host:port/database")
        database_url = input("DATABASE_URL: ").strip()
        
        if not database_url:
            print("❌ No database URL provided. Exiting.")
            sys.exit(1)
    
    # Convert postgres:// to postgresql:// for SQLAlchemy
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return database_url

def connect_to_database():
    """Create database connection"""
    database_url = get_database_url()
    
    try:
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={
                'connect_timeout': 10,
            }
        )
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"✅ Connected to PostgreSQL: {version.split(',')[0]}")
        
        return engine
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        sys.exit(1)

def list_tables(engine):
    """List all tables in the database"""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\n📊 Found {len(tables)} table(s):")
    for table in tables:
        print(f"  - {table}")
    return tables

def describe_table(engine, table_name):
    """Describe table structure"""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        print(f"❌ Table '{table_name}' not found")
        return
    
    columns = inspector.get_columns(table_name)
    print(f"\n📋 Table: {table_name}")
    print(tabulate(
        [{'Column': col['name'], 'Type': str(col['type']), 'Nullable': col['nullable']} 
         for col in columns],
        headers='keys',
        tablefmt='grid'
    ))

def execute_query(engine, query):
    """Execute a SQL query and return results"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            
            # Check if it's a SELECT query (has rows)
            if result.returns_rows:
                rows = result.fetchall()
                columns = result.keys()
                
                if rows:
                    # Convert to list of dicts for tabulate
                    results = [dict(zip(columns, row)) for row in rows]
                    print(tabulate(results, headers='keys', tablefmt='grid'))
                    print(f"\n✅ Returned {len(rows)} row(s)")
                else:
                    print("✅ Query executed successfully (no rows returned)")
            else:
                print("✅ Query executed successfully")
                conn.commit()
    except Exception as e:
        print(f"❌ Error executing query: {e}")

def interactive_mode(engine):
    """Interactive query mode"""
    print("\n" + "="*60)
    print("📊 Interactive Database Query Mode")
    print("="*60)
    print("Commands:")
    print("  - Type SQL queries to execute")
    print("  - '\\tables' - List all tables")
    print("  - '\\describe <table>' - Describe table structure")
    print("  - '\\exit' or '\\quit' - Exit")
    print("="*60 + "\n")
    
    while True:
        try:
            query = input("db> ").strip()
            
            if not query:
                continue
            
            # Handle special commands
            if query.lower() in ['\\exit', '\\quit', 'exit', 'quit']:
                print("👋 Goodbye!")
                break
            elif query.lower() == '\\tables':
                list_tables(engine)
                continue
            elif query.lower().startswith('\\describe '):
                table_name = query.split(' ', 1)[1] if len(query.split(' ', 1)) > 1 else None
                if table_name:
                    describe_table(engine, table_name)
                else:
                    print("❌ Usage: \\describe <table_name>")
                continue
            
            # Execute SQL query
            execute_query(engine, query)
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except EOFError:
            print("\n👋 Goodbye!")
            break

def main():
    """Main function"""
    print("🔌 Connecting to database...")
    engine = connect_to_database()
    
    # List tables
    tables = list_tables(engine)
    
    # Quick stats
    print("\n📈 Quick Statistics:")
    try:
        with engine.connect() as conn:
            # Count users
            result = conn.execute(text("SELECT COUNT(*) FROM users;"))
            user_count = result.fetchone()[0]
            print(f"  👥 Users: {user_count}")
            
            # Count emails
            if 'email_classifications' in tables:
                result = conn.execute(text("SELECT COUNT(*) FROM email_classifications;"))
                email_count = result.fetchone()[0]
                print(f"  📧 Emails: {email_count}")
            
            # Count Gmail tokens
            if 'gmail_tokens' in tables:
                result = conn.execute(text("SELECT COUNT(*) FROM gmail_tokens;"))
                token_count = result.fetchone()[0]
                print(f"  🔑 Gmail Tokens: {token_count}")
    except Exception as e:
        print(f"  ⚠️  Could not fetch statistics: {e}")
    
    # Enter interactive mode
    interactive_mode(engine)

def clear_all_rows(engine):
    """Clear all rows from specified tables in correct order (respecting foreign keys)"""
    print("🗑️  Clearing all rows from database...")
    tables_to_clear = ['deals', 'email_classifications', 'gmail_tokens', 'users']
    
    with engine.connect() as conn:
        for table_name in tables_to_clear:
            try:
                result = conn.execute(text(f"DELETE FROM {table_name};"))
                print(f"✅ Cleared {result.rowcount} rows from {table_name}")
            except Exception as e:
                print(f"❌ Error clearing table {table_name}: {e}")
        conn.commit()
    print("\n✅ Database cleared successfully!")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'clear':
        engine = connect_to_database()
        clear_all_rows(engine)
        # Show stats after clearing
        print("\n📈 Quick Statistics (after clearing):")
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM users;"))
                print(f"  👥 Users: {result.fetchone()[0]}")
                result = conn.execute(text("SELECT COUNT(*) FROM email_classifications;"))
                print(f"  📧 Emails: {result.fetchone()[0]}")
                result = conn.execute(text("SELECT COUNT(*) FROM gmail_tokens;"))
                print(f"  🔑 Gmail Tokens: {result.fetchone()[0]}")
        except Exception as e:
            print(f"  ⚠️  Could not fetch statistics: {e}")
    else:
        main()


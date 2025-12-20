import streamlit as st
import json
import re
from pathlib import Path


# ============================================================================
# DEFAULT VALUES - Edit these to change the pre-filled values in the form
# ============================================================================

# Source Parameters Defaults
DEFAULT_POSTGRES_JDBC_URL = "jdbc:postgresql://yourrandomid.org-accname.region.csp.postgres.snowflake.app:5432/demodb"
DEFAULT_POSTGRES_USERNAME = "snowflake_admin"
DEFAULT_POSTGRES_PUBLICATION_NAME = "retail_openflow_sync"

# Destination Parameters Defaults
DEFAULT_SNOWFLAKE_ACCOUNT_ID = "myorg-sf-accountname"
DEFAULT_SNOWFLAKE_USERNAME = "your_userid"
DEFAULT_SNOWFLAKE_ROLE = "sysadmin"
DEFAULT_SNOWFLAKE_WAREHOUSE = "COMPUTE_WH"
DEFAULT_SNOWFLAKE_DATABASE = "retailcdc_db"

# Ingestion Parameters Defaults
DEFAULT_TABLE_REGEX = "retail\\..*"

# ============================================================================


# Define the variables organized by section with their metadata
VARIABLES = {
    "source": {
        "title": "PostgreSQL Source Parameters",
        "icon": "🐘",
        "description": "Configure your PostgreSQL source database connection settings",
        "variables": {
            "$$POSTGRESS_JDBC_URL$$": {
                "label": "PostgreSQL Connection URL",
                "help": "The JDBC Connection URL (e.g., jdbc:postgresql://host:5432/database)",
                "default": DEFAULT_POSTGRES_JDBC_URL
            },
            "$$POSTGRES_USERNMAME$$": {
                "label": "PostgreSQL Username",
                "help": "The username for interacting with PostgreSQL",
                "default": DEFAULT_POSTGRES_USERNAME
            },
            "$$POSTGRES_PUBLICATION_NAME$$": {
                "label": "Publication Name",
                "help": "The name of the publication created in PostgreSQL database",
                "default": DEFAULT_POSTGRES_PUBLICATION_NAME
            },
        }
    },
    "destination": {
        "title": "Snowflake Destination Parameters",
        "icon": "❄️",
        "description": "Configure your Snowflake destination settings",
        "variables": {
            "$$SNOWFLAKEORG-ACCOUNTNAME$$": {
                "label": "Snowflake Account Identifier",
                "help": "Your Snowflake account formatted as [organization-name]-[account-name]",
                "default": DEFAULT_SNOWFLAKE_ACCOUNT_ID
            },
            "$$SNOWFLAKE_USERNAME$$": {
                "label": "Snowflake Username",
                "help": "The user name used to connect to Snowflake instance",
                "default": DEFAULT_SNOWFLAKE_USERNAME
            },
            "$$SNOWFLAKE_ROLE$$": {
                "label": "Snowflake Role",
                "help": "The Snowflake role to use for authentication",
                "default": DEFAULT_SNOWFLAKE_ROLE
            },
            "$$WAREHOUSE$$": {
                "label": "Snowflake Warehouse",
                "help": "Snowflake warehouse used to run queries",
                "default": DEFAULT_SNOWFLAKE_WAREHOUSE
            },
            "$$SNOWFLAKE_DATABASE$$": {
                "label": "Destination Database",
                "help": "The database where data will be persisted. It must already exist in Snowflake",
                "default": DEFAULT_SNOWFLAKE_DATABASE
            },
        }
    },
    "ingestion": {
        "title": "PostgreSQL Ingestion Parameters",
        "icon": "⚙️",
        "description": "Configure ingestion behavior and table filtering",
        "variables": {
            "$$POSTGRES_TABLE_TO_REPLICATE_REGEX$$": {
                "label": "Included Table Regex",
                "help": "A Regular Expression to match table names for replication (e.g., public\\..*)",
                "default": DEFAULT_TABLE_REGEX
            },
        }
    }
}


def load_template():
    """Load the template JSON file."""
    template_path = Path(__file__).parent / "postgres_cdc_openflow.json"
    with open(template_path, 'r') as f:
        return f.read()


def extract_variables(content):
    """Extract all $$VARIABLE$$ patterns from the content."""
    pattern = r'\$\$[A-Za-z0-9_-]+\$\$'
    return list(set(re.findall(pattern, content)))


def escape_json_value(value):
    """Escape special characters for JSON string values."""
    # Use json.dumps to properly escape, then strip the surrounding quotes
    escaped = json.dumps(value)
    # Remove the surrounding quotes that json.dumps adds
    return escaped[1:-1]


def replace_variables(content, replacements):
    """Replace all variables with their values."""
    result = content
    for var, value in replacements.items():
        # Escape the value for JSON compatibility
        escaped_value = escape_json_value(value)
        result = result.replace(var, escaped_value)
    return result


def main():
    st.set_page_config(
        page_title="Openflow Configuration Generator",
        page_icon="🔄",
        layout="wide"
    )
    
    # Custom CSS - Light Theme with good contrast
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Outfit:wght@300;400;600;700&display=swap');
        
        .stApp {
            background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 50%, #f1f5f9 100%);
        }
        
        .main-header {
            font-family: 'Outfit', sans-serif;
            font-size: 2.8rem;
            font-weight: 700;
            background: linear-gradient(120deg, #0891b2, #7c3aed, #db2777);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            padding: 1.5rem 0;
            margin-bottom: 0.5rem;
        }
        
        .subtitle {
            font-family: 'Outfit', sans-serif;
            color: #475569;
            text-align: center;
            font-size: 1.1rem;
            margin-bottom: 2rem;
        }
        
        .section-card {
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            border: 2px solid #e2e8f0;
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }
        
        .section-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.4rem;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 0.5rem;
        }
        
        .section-desc {
            font-family: 'Outfit', sans-serif;
            color: #64748b;
            font-size: 0.9rem;
            margin-bottom: 1rem;
        }
        
        .stTextInput > label {
            font-family: 'Outfit', sans-serif !important;
            color: #334155 !important;
            font-weight: 600 !important;
        }
        
        .stTextInput > div > div > input {
            font-family: 'JetBrains Mono', monospace !important;
            background: #ffffff !important;
            border: 2px solid #cbd5e1 !important;
            border-radius: 8px !important;
            color: #0f172a !important;
            font-size: 1rem !important;
            padding: 0.75rem !important;
        }
        
        .stTextInput > div > div > input::placeholder {
            color: #94a3b8 !important;
        }
        
        .stTextInput > div > div > input:focus {
            border-color: #7c3aed !important;
            box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.15) !important;
        }
        
        .stButton > button {
            font-family: 'Outfit', sans-serif !important;
            font-weight: 600 !important;
            background: linear-gradient(135deg, #7c3aed, #0891b2) !important;
            color: white !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 0.75rem 2rem !important;
            font-size: 1.1rem !important;
            transition: all 0.3s ease !important;
        }
        
        .stButton > button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 25px rgba(124, 58, 237, 0.3) !important;
        }
        
        .stDownloadButton > button {
            font-family: 'Outfit', sans-serif !important;
            font-weight: 600 !important;
            background: linear-gradient(135deg, #059669, #10b981) !important;
            color: white !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 0.75rem 2rem !important;
            font-size: 1.1rem !important;
            width: 100% !important;
        }
        
        .success-box {
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.1), rgba(5, 150, 105, 0.05));
            border: 2px solid #10b981;
            border-radius: 12px;
            padding: 1rem;
            margin-top: 1rem;
        }
        
        .stExpander {
            background: #ffffff !important;
            border: 2px solid #e2e8f0 !important;
            border-radius: 12px !important;
        }
        
        div[data-testid="stExpander"] details summary p {
            font-family: 'Outfit', sans-serif !important;
            font-weight: 500 !important;
            color: #334155 !important;
        }
        
        .footer {
            text-align: center;
            color: #64748b;
            font-family: 'Outfit', sans-serif;
            margin-top: 3rem;
            padding-bottom: 2rem;
        }
        
        /* Info and success message styling */
        .stAlert {
            background: #ffffff !important;
            border-radius: 8px !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<h1 class="main-header">🔄 Openflow Configuration Generator</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Configure your PostgreSQL to Snowflake CDC pipeline</p>', unsafe_allow_html=True)
    
    # Initialize session state for inputs
    if 'inputs' not in st.session_state:
        st.session_state.inputs = {}
    
    # Create three columns for the three sections
    col1, col2, col3 = st.columns(3)
    
    all_inputs = {}
    
    # Source Parameters Section
    with col1:
        section = VARIABLES["source"]
        st.markdown(f"""
            <div class="section-card">
                <div class="section-title">{section['icon']} {section['title']}</div>
                <div class="section-desc">{section['description']}</div>
            </div>
        """, unsafe_allow_html=True)
        
        for var_key, var_info in section["variables"].items():
            value = st.text_input(
                var_info["label"],
                value=var_info["default"],
                help=var_info["help"],
                key=f"source_{var_key}"
            )
            all_inputs[var_key] = value
    
    # Destination Parameters Section
    with col2:
        section = VARIABLES["destination"]
        st.markdown(f"""
            <div class="section-card">
                <div class="section-title">{section['icon']} {section['title']}</div>
                <div class="section-desc">{section['description']}</div>
            </div>
        """, unsafe_allow_html=True)
        
        for var_key, var_info in section["variables"].items():
            value = st.text_input(
                var_info["label"],
                value=var_info["default"],
                help=var_info["help"],
                key=f"dest_{var_key}"
            )
            all_inputs[var_key] = value
    
    # Ingestion Parameters Section
    with col3:
        section = VARIABLES["ingestion"]
        st.markdown(f"""
            <div class="section-card">
                <div class="section-title">{section['icon']} {section['title']}</div>
                <div class="section-desc">{section['description']}</div>
            </div>
        """, unsafe_allow_html=True)
        
        for var_key, var_info in section["variables"].items():
            value = st.text_input(
                var_info["label"],
                value=var_info["default"],
                help=var_info["help"],
                key=f"ing_{var_key}"
            )
            all_inputs[var_key] = value
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Check if all fields are filled
    all_filled = all(v.strip() for v in all_inputs.values())
    
    # Generate Configuration Section
    st.markdown("---")
    
    col_left, col_center, col_right = st.columns([1, 2, 1])
    
    with col_center:
        if st.button("🚀 Generate Configuration", use_container_width=True, disabled=not all_filled):
            try:
                # Load template
                template_content = load_template()
                
                # Replace variables
                output_content = replace_variables(template_content, all_inputs)
                
                # Validate JSON
                json.loads(output_content)
                
                st.session_state.generated_config = output_content
                st.session_state.generation_success = True
                
            except json.JSONDecodeError as e:
                st.error(f"❌ Error generating JSON: {e}")
            except Exception as e:
                st.error(f"❌ Error: {e}")
        
        if not all_filled:
            st.info("💡 Please fill in all fields to generate the configuration")
    
    # Show download button and preview if generation was successful
    if st.session_state.get('generation_success'):
        st.markdown("<br>", unsafe_allow_html=True)
        
        col_dl_left, col_dl_center, col_dl_right = st.columns([1, 2, 1])
        
        with col_dl_center:
            st.markdown('<div class="success-box">', unsafe_allow_html=True)
            st.success("✅ Configuration generated successfully!")
            
            st.download_button(
                label="📥 Download Configuration JSON",
                data=st.session_state.generated_config,
                file_name="postgres_cdc_openflow_configured.json",
                mime="application/json",
                use_container_width=True
            )
            st.markdown('</div>', unsafe_allow_html=True)
        
        # Preview section
        with st.expander("👁️ Preview Generated Configuration", expanded=False):
            # Show just the parameterContexts section for preview
            try:
                config_json = json.loads(st.session_state.generated_config)
                param_contexts = config_json.get("parameterContexts", {})
                st.json(param_contexts)
            except:
                st.code(st.session_state.generated_config[:5000] + "\n...(truncated)", language="json")
    
    # Footer
    st.markdown("""
        <div class="footer">
            <p>Openflow Configuration Generator • PostgreSQL CDC to Snowflake</p>
        </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()


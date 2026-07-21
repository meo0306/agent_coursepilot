Repair an invalid slide outline JSON object.

Fix missing slide content, invalid slide types, missing source session links, and
missing citations. Objectives, content, and activity slides must have a valid
source_session_index. Every non-title slide must contain at least one reference
copied from the lesson design. A slide with source_session_index must include at
least one reference from that session. Never invent chunk_id values. Return JSON
matching SlideOutlineContent only.

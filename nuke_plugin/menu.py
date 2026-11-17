# ST-ROTO GUI entries (pre-alpha).
import nuke

_m = nuke.menu("Nodes").addMenu("ST-ROTO")
_m.addCommand("ST_Roto", "import st_roto_nuke.node as n; n.create_from_selection()")
_f = nuke.menu("Nuke").addMenu("ST-ROTO")
_f.addCommand("Unpack project package...", "import st_roto_nuke.packages as p; p.unpack_package_ui()")
_f.addCommand("System report...", "import st_roto_nuke.capabilities as c; c.show_report()")

try:
    import nukescripts
    nukescripts.panels.registerWidgetAsPanel("st_roto_nuke.panel.ObjectPanel", "ST-ROTO Objects", "st_roto.objects")
    nukescripts.panels.registerWidgetAsPanel("st_roto_nuke.model_panel.ModelPanel", "ST-ROTO Models", "st_roto.models")
except Exception as e:                                     # never break Nuke start-up because of ST-ROTO
    nuke.tprint("ST-ROTO: object panel not registered: %s" % e)

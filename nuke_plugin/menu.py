# ST-ROTO GUI entries (pre-alpha).
import nuke

_m = nuke.menu("Nodes").addMenu("ST-ROTO")
_m.addCommand("ST_Roto", "import st_roto_nuke.node as n; n.create_from_selection()")

try:
    import nukescripts
    nukescripts.panels.registerWidgetAsPanel("st_roto_nuke.panel.ObjectPanel", "ST-ROTO Objects", "st_roto.objects")
except Exception as e:                                     # never break Nuke start-up because of ST-ROTO
    nuke.tprint("ST-ROTO: object panel not registered: %s" % e)

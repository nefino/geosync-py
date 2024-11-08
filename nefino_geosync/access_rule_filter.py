
class AccessRuleFilter:
    def __init__(self, access_rules):
        self.access_rules = access_rules

    def check(self, place, cluster):
        for access_rule in self.access_rules:
            if place in access_rule.places:
                if access_rule.all_clusters_enabled or cluster in access_rule.clusters:
                    return True
        return False
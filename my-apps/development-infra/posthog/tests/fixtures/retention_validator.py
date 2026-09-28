"""Pinned PostHog 065179102 API method, kept verbatim for the drift guard test."""

class TeamSerializer:
    def _verify_update_session_recording_retention_period(self, instance: Team, new_retention_period: str):
        retention_feature = instance.organization.get_available_feature(AvailableFeature.SESSION_REPLAY_DATA_RETENTION)
        highest_retention_entitlement = parse_feature_to_entitlement(retention_feature)

        if highest_retention_entitlement is None:
            raise exceptions.APIException(detail="Invalid retention entitlement.")  # HTTP 500

        # Should be validated already, but let's be extra sure to avoid IndexErrors below
        if not validate_retention_period(new_retention_period):
            raise exceptions.ValidationError(  # HTTP 400
                f"Must provide a valid retention period. Options are: {VALID_RETENTION_PERIODS}."
            )

        if retention_violates_entitlement(new_retention_period, highest_retention_entitlement):
            raise exceptions.PermissionDenied(  # HTTP 403
                f"This organization does not have permission to set retention period of length '{new_retention_period}' - longest allowable retention period is '{highest_retention_entitlement}'."
            )

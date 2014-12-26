(function() {
  var app;

  app = angular.module("ng-tank-manager", ['ui.ace', 'ui.bootstrap']);

  app.constant("TEST_STAGES", ['lock', 'init', 'configure', 'prepare', 'start', 'poll', 'end', 'postprocess', 'unlock', 'finish']);

  app.constant("_", window._);

  app.controller("TankManager", function($scope, $interval, $http, TEST_STAGES, _) {
    var updateStatus;
    $scope.max_progress = TEST_STAGES.length;
    updateStatus = function() {
      return $http.get("status").success(function(data) {
        $scope.status = data;
        if ($scope.current_session != null) {
          $scope.session_status = data[$scope.current_session].current_stage;
          return $scope.progress = _.indexOf(TEST_STAGES, $scope.session_status);
        }
      });
    };
    $scope.runTest = function() {
      return $http.post("run", $scope.tankConfig).success(function(data) {
        $scope.reply = data;
        $scope.current_test = data.test;
        return $scope.current_session = data.session;
      });
    };
    $scope.stopTest = function() {
      return $http.get("stop?session=" + $scope.current_session).success(function(data) {
        return $scope.reply = data;
      });
    };
    return $interval(updateStatus, 1000);
  });

}).call(this);

(function() {
  var app;

  app = angular.module("ng-tank-manager", ['ui.ace']);

  app.controller("TankManager", function($scope, $interval, $http) {
    var updateStatus;
    updateStatus = function() {
      return $http.get("status").success(function(data) {
        $scope.status = data;
        if ($scope.current_session != null) {
          return $scope.session_status = data[$scope.current_session].current_stage;
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
